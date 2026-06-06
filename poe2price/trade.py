"""Talk to the official Path of Exile 2 trade API.

Endpoints (note the ``trade2`` / ``poe2`` path segments)::

    POST https://www.pathofexile.com/api/trade2/search/poe2/<league>
    GET  https://www.pathofexile.com/api/trade2/fetch/<id,id,...>?query=<search-id>

The search returns an ordered list of result ids plus a search id; ``fetch``
turns up to 10 ids at a time into full listings.  The site is behind
Cloudflare and rate-limited, so a valid ``POESESSID`` cookie and a polite
request rate matter (see :mod:`poe2price.config`).

NOTE: the exact query schema is still being validated against the live API.
The builders below cover name/base searches (currency, uniques, gems); stat
filters for rares/magics are phase 2.
"""

from __future__ import annotations

import statistics
import time
import urllib.parse
from collections import Counter
from dataclasses import dataclass

import requests

from .parser import Item
from .stats import (
    StatsIndex,
    build_stat_filters,
    load_currency_map,
    load_stats_index,
)

API = "https://www.pathofexile.com/api/trade2"
SITE = "https://www.pathofexile.com/trade2/search/poe2"
SITE_EXCHANGE = "https://www.pathofexile.com/trade2/exchange/poe2"

# Reference currency that other currencies are priced in (PoE2's base unit).
_REFERENCE_CURRENCY = "exalted"
_REFERENCE_FALLBACK = "divine"  # used when pricing exalted itself

# Fewer than this many comparable listings -> flag the price as uncertain.
_LOW_CONFIDENCE_COUNT = 3

# The trade API intermittently returns these; a retry almost always succeeds.
_RETRYABLE_STATUS = {500, 502, 503, 504}
_MAX_ATTEMPTS = 3
_RETRY_BACKOFF = 0.6  # seconds; doubled each retry

# Proactive rate-limit spacing. The API advertises buckets like "3:5:60"
# (3 hits / 5s / 60s ban) plus current usage. We only slow down when a bucket
# is near its ceiling, then to its sustainable rate (period/max_hits), capped
# so even the widest bucket (e.g. 60:300 -> 5s) stays reasonable.
_MAX_SPACING = 6.0
# Auto-wait through a 429 only if the advertised wait is this short; longer
# bans are surfaced to the user instead of blocking.
_MAX_429_RETRY_WAIT = 12.0


class TradeError(Exception):
    """A user-facing problem talking to the trade API."""


@dataclass
class Listing:
    amount: float | None
    currency: str | None
    account: str | None
    whisper: str | None

    @property
    def price_text(self) -> str:
        if self.amount is None:
            return "no price"
        return f"{_fmt_amount(self.amount)} {self.currency or ''}".strip()


@dataclass
class PriceSummary:
    """Aggregate price across listings, in the most common currency."""

    count: int                  # listings counted (in the dominant currency)
    currency: str | None
    low: float | None
    median: float | None

    @property
    def low_confidence(self) -> bool:
        """True when there are too few data points to trust the price."""
        return 0 < self.count < _LOW_CONFIDENCE_COUNT

    @property
    def text(self) -> str:
        if not self.count or self.median is None:
            return "no price data"
        cur = self.currency or ""
        if self.low is not None and self.low != self.median:
            body = (f"~{_fmt_amount(self.median)} {cur} "
                    f"(low {_fmt_amount(self.low)}, {self.count} listings)")
        else:
            body = f"~{_fmt_amount(self.median)} {cur} ({self.count} listings)"
        if self.low_confidence:
            body += " — few data points"
        return body.strip()


def _fmt_amount(amount: float) -> str:
    return str(int(amount)) if amount == int(amount) else str(round(amount, 4))


def summarize(listings: list[Listing]) -> PriceSummary:
    """Summarise *listings* using the most common currency.

    Median is robust against the occasional lowball/bait listing the trade and
    exchange endpoints surface at the top.
    """
    priced = [x for x in listings if x.amount is not None and x.currency]
    if not priced:
        return PriceSummary(0, None, None, None)
    dominant, _ = Counter(x.currency for x in priced).most_common(1)[0]
    amounts = sorted(x.amount for x in priced if x.currency == dominant)
    return PriceSummary(
        count=len(amounts),
        currency=dominant,
        low=amounts[0],
        median=statistics.median(amounts),
    )


class TradeClient:
    def __init__(self, cfg) -> None:
        self.cfg = cfg
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": cfg.user_agent,
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Origin": "https://www.pathofexile.com",
            "Referer": f"{SITE}/{urllib.parse.quote(cfg.league)}",
        })
        if cfg.poesessid:
            self.session.cookies.set(
                "POESESSID", cfg.poesessid, domain=".pathofexile.com"
            )
        # Stat catalog for rare/magic searches; loaded lazily on first use.
        # None = not loaded yet, False = load failed (don't keep retrying).
        self._stats_index = None
        self._currency_map = None  # name -> exchange id, lazily loaded
        # Per-endpoint throttle state: label -> (min_interval, last_monotonic).
        self._throttle: dict[str, tuple[float, float]] = {}

    # -- public API ---------------------------------------------------------

    def stats_index(self):
        """The stat catalog, loaded lazily. Returns None if it can't be loaded."""
        if self._stats_index is None:
            try:
                self._stats_index = load_stats_index(self.session)
            except Exception:
                self._stats_index = False
        return self._stats_index or None

    def currency_map(self):
        """The currency name->id map, loaded lazily. None if unavailable."""
        if self._currency_map is None:
            try:
                self._currency_map = load_currency_map(self.session)
            except Exception:
                self._currency_map = False
        return self._currency_map or None

    def check_session(self) -> tuple[bool, str]:
        """Validate the configured POESESSID.

        Returns ``(ok, message)``. ``ok`` is True only when the cookie
        authenticates against pathofexile.com. Used for the startup warning.
        """
        if not self.cfg.poesessid:
            return False, "no POESESSID configured"
        try:
            resp = self.session.get(
                "https://www.pathofexile.com/api/profile", timeout=10
            )
        except requests.RequestException as exc:
            return False, f"could not reach pathofexile.com ({exc})"

        if resp.status_code == 200:
            try:
                name = resp.json().get("name")
            except ValueError:
                name = None
            if name:
                return True, f"authenticated as {name}"
            return False, "POESESSID did not return a profile (likely expired)"
        if resp.status_code in (401, 403):
            return False, "POESESSID rejected — log in again and copy a fresh cookie"
        return False, f"unexpected status {resp.status_code} while checking session"

    def price_item(self, item: Item) -> tuple[list[Listing], str, str]:
        """Return (listings, trade_site_url, search_summary) for *item*.

        Currency is priced via the bulk exchange endpoint; everything else via
        the search endpoint. The summary describes what we actually searched by
        (e.g. "base + 4 stat filters") so the result is never a mystery.
        """
        if self._is_currency(item):
            result = self._price_currency(item)
            if result is not None:
                return result
            # fall through to a normal search if the currency isn't recognised

        plan = plan_search(item, self.stats_index(), self._status())
        search = self._post_search(plan.query)
        result_ids = search.get("result") or []
        search_id = search.get("id")
        url = f"{SITE}/{urllib.parse.quote(self.cfg.league)}/{search_id}"
        if not result_ids:
            return [], url, plan.summary
        listings = self._fetch(result_ids[: self.cfg.max_listings], search_id)
        return listings, url, plan.summary

    def _status(self) -> str:
        """The configured listing status, defaulting to 'online' if invalid."""
        return "any" if str(getattr(self.cfg, "status", "online")).lower() == "any" else "online"

    @staticmethod
    def _is_currency(item: Item) -> bool:
        return item.rarity == "Currency" or (
            (item.item_class or "").strip().lower()
            in {"stackable currency", "currency"}
        )

    def _price_currency(self, item: Item) -> tuple[list[Listing], str, str] | None:
        """Price currency via the bulk exchange endpoint. None if unrecognised."""
        cmap = self.currency_map()
        want = cmap.get(item.base_type or item.name or "") if cmap else None
        if not want:
            return None
        have = _REFERENCE_CURRENCY if want != _REFERENCE_CURRENCY else _REFERENCE_FALLBACK
        body = {
            "query": {"status": {"option": self._status()}, "have": [have], "want": [want]},
            "sort": {"have": "asc"},
            "engine": "new",
        }
        league = urllib.parse.quote(self.cfg.league)
        data = self._send("POST", f"{API}/exchange/{league}", json=body).json()
        url = f"{SITE_EXCHANGE}/{league}/{data.get('id')}"
        listings = _exchange_listings(data, self.cfg.max_listings)
        summary = f"exchange: {want} priced in {have}"
        return listings, url, summary

    # -- HTTP ---------------------------------------------------------------

    def _post_search(self, query: dict) -> dict:
        url = f"{API}/search/poe2/{urllib.parse.quote(self.cfg.league)}"
        return self._send("POST", url, json=query).json()

    def _fetch(self, ids: list[str], search_id: str) -> list[Listing]:
        listings: list[Listing] = []
        for start in range(0, len(ids), 10):
            batch = ids[start : start + 10]
            url = f"{API}/fetch/{','.join(batch)}"
            resp = self._send("GET", url, params={"query": search_id})
            for entry in resp.json().get("result") or []:
                listings.append(_to_listing(entry))
        return listings

    def _send(self, method: str, url: str, **kwargs) -> requests.Response:
        """Send a request with proactive throttling and retries.

        Retries transient 5xx with backoff and auto-waits through short 429
        bans; long bans are surfaced to the user.
        """
        label = self._endpoint_label(url)
        backoff = _RETRY_BACKOFF
        for attempt in range(1, _MAX_ATTEMPTS + 1):
            last = attempt == _MAX_ATTEMPTS
            self._await_throttle(label)
            try:
                resp = self.session.request(method, url, timeout=15, **kwargs)
            except requests.RequestException as exc:
                if last:
                    raise TradeError(f"Could not reach the trade API: {exc}") from exc
                time.sleep(backoff)
                backoff *= 2
                continue
            self._learn_throttle(label, resp)
            if resp.status_code == 429:
                wait = self._retry_after_seconds(resp)
                if not last and wait <= _MAX_429_RETRY_WAIT:
                    time.sleep(wait)
                    continue
                raise TradeError(
                    f"Rate limited by the trade API. Try again in about "
                    f"{int(wait)}s."
                )
            if resp.status_code in _RETRYABLE_STATUS and not last:
                time.sleep(backoff)
                backoff *= 2
                continue
            self._raise_for_status(resp)
            return resp
        # Unreachable: the loop either returns or raises on the final attempt.
        raise TradeError("Trade API request failed after retries.")

    @staticmethod
    def _endpoint_label(url: str) -> str:
        for marker in ("search", "fetch", "exchange"):
            if f"/{marker}/" in url or url.endswith(f"/{marker}"):
                return marker
        return "other"

    def _await_throttle(self, label: str) -> None:
        """Sleep just enough to keep under the learned rate-limit spacing."""
        interval, last = self._throttle.get(label, (0.0, 0.0))
        if interval > 0.0:
            elapsed = time.monotonic() - last
            if elapsed < interval:
                time.sleep(interval - elapsed)

    def _learn_throttle(self, label: str, resp: requests.Response) -> None:
        """Update the spacing for *label* from the response's limit headers.

        Spacing is only applied for buckets at/near their ceiling, so we run at
        full speed while there's headroom and ease off just before a ban.
        """
        spacing = 0.0
        pairs = (
            ("X-Rate-Limit-Account", "X-Rate-Limit-Account-State"),
            ("X-Rate-Limit-Ip", "X-Rate-Limit-Ip-State"),
        )
        for rule_header, state_header in pairs:
            rules = resp.headers.get(rule_header)
            if not rules:
                continue
            states = (resp.headers.get(state_header) or "").split(",")
            for i, bucket in enumerate(rules.split(",")):
                parts = bucket.split(":")
                if len(parts) < 2:
                    continue
                try:
                    max_hits, period = int(parts[0]), int(parts[1])
                except ValueError:
                    continue
                if max_hits <= 0:
                    continue
                current = 0
                if i < len(states):
                    try:
                        current = int(states[i].split(":")[0])
                    except (ValueError, IndexError):
                        current = 0
                if current >= max_hits - 1:  # at or one below the ceiling
                    spacing = max(spacing, period / max_hits)
        self._throttle[label] = (min(spacing, _MAX_SPACING), time.monotonic())

    @staticmethod
    def _retry_after_seconds(resp: requests.Response) -> float:
        """How long the API wants us to wait after a 429."""
        header = resp.headers.get("Retry-After")
        if header:
            try:
                return float(header)
            except ValueError:
                pass
        # Fall back to the largest active restriction in the state headers.
        wait = 5.0
        for name in ("X-Rate-Limit-Account-State", "X-Rate-Limit-Ip-State"):
            state = resp.headers.get(name)
            if not state:
                continue
            for bucket in state.split(","):
                parts = bucket.split(":")
                if len(parts) >= 3:
                    try:
                        wait = max(wait, float(parts[2]))
                    except ValueError:
                        pass
        return wait

    def _raise_for_status(self, resp: requests.Response) -> None:
        if resp.status_code == 429:
            retry = resp.headers.get("Retry-After", "a few")
            raise TradeError(f"Rate limited by the trade API. Retry after {retry}s.")
        if resp.status_code in (401, 403):
            raise TradeError(
                "Blocked by Cloudflare / not authorised. "
                "Set a fresh POESESSID in the config."
            )
        if resp.status_code in _RETRYABLE_STATUS:
            raise TradeError(
                "The trade API is having a moment (server error). "
                "Try again in a few seconds."
            )
        if not resp.ok:
            raise TradeError(f"Trade API error {resp.status_code}: {resp.text[:200]}")


def _to_listing(entry: dict) -> Listing:
    listing = entry.get("listing") or {}
    price = listing.get("price") or {}
    account = (listing.get("account") or {}).get("name")
    return Listing(
        amount=price.get("amount"),
        currency=price.get("currency"),
        account=account,
        whisper=listing.get("whisper"),
    )


@dataclass
class SearchPlan:
    """A built search body plus a human description of what it searches by."""

    query: dict
    summary: str


def plan_search(
    item: Item, stats_index: StatsIndex | None = None, status: str = "online"
) -> SearchPlan:
    """Plan a trade2 search for *item*.

    Uniques search by name (+ base type); name-searchable items by base type.
    Rares/magics search by base type **plus stat filters** from their mods
    (pseudo-folded, relaxed mins) when *stats_index* is available. The summary
    explains the choice so a base-only fallback is never silent. *status* is the
    listing status filter ("online" or "any").
    """
    query: dict = {"status": {"option": status}}

    if item.rarity == "Unique" and item.name:
        query["name"] = item.name
        if item.base_type:
            query["type"] = item.base_type
        return SearchPlan(_wrap(query), f"by name: {item.name}")

    if item.name_searchable and item.base_type:
        query["type"] = item.base_type
        return SearchPlan(_wrap(query), f"by base: {item.base_type}")

    # Rare / Magic (and anything else with mods): base type + stat filters.
    if item.base_type:
        query["type"] = item.base_type

    filters = build_stat_filters(item, stats_index) if stats_index else []
    if filters:
        query["stats"] = [{"type": "and", "filters": filters}]
        base = item.base_type or "any base"
        summary = f"{base} + {len(filters)} stat filter{'s' * (len(filters) != 1)}"
    elif item.base_type:
        summary = "base only — no mods matched the catalog"
    elif item.name:
        query["term"] = item.name  # last resort when we have nothing else
        summary = f"by text: {item.name}"
    else:
        summary = "everything (could not identify item)"

    return SearchPlan(_wrap(query), summary)


def build_query(item: Item, stats_index: StatsIndex | None = None) -> dict:
    """Backward-compatible helper returning just the query body."""
    return plan_search(item, stats_index).query


def _wrap(query: dict) -> dict:
    return {"query": query, "sort": {"price": "asc"}}


def _exchange_listings(data: dict, limit: int) -> list[Listing]:
    """Parse bulk-exchange results into per-unit Listings of the want currency."""
    listings: list[Listing] = []
    result = data.get("result") or {}
    entries = result.values() if isinstance(result, dict) else result
    for entry in entries:
        listing = entry.get("listing") or {}
        offers = listing.get("offers") or []
        if not offers:
            continue
        offer = offers[0]
        pay = offer.get("exchange") or {}       # what the buyer gives (have)
        get = offer.get("item") or {}           # what they receive (want)
        have_amount = pay.get("amount")
        want_amount = get.get("amount")
        if not want_amount:
            continue
        unit_price = have_amount / want_amount  # have-currency per 1 want
        account = (listing.get("account") or {}).get("name")
        listings.append(Listing(
            amount=round(unit_price, 4),
            currency=pay.get("currency"),
            account=account,
            whisper=listing.get("whisper"),
        ))
        if len(listings) >= limit:
            break
    return listings
