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
from dataclasses import dataclass, field

import requests

from .parser import Item
from .stats import (
    StatFilter,
    StatsIndex,
    build_filter_model,
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

# When the initial auto-search ANDs too many mods and matches nothing, relax at
# most this many of the lowest-priority stat filters before giving up.
_MAX_RELAX_DROPS = 4

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
    high: float | None = None   # priciest of the sampled listings

    @property
    def low_confidence(self) -> bool:
        """True when there are too few data points to trust the price."""
        return 0 < self.count < _LOW_CONFIDENCE_COUNT

    @property
    def headline(self) -> str:
        """The big number: ``~81 exalted`` (or a no-data note)."""
        if not self.count or self.median is None:
            return "no price data"
        return f"~{_fmt_amount(self.median)} {self.currency or ''}".strip()

    @property
    def detail(self) -> str:
        """The secondary line: listing count, low, confidence."""
        if not self.count or self.median is None:
            return ""
        parts = [f"{self.count} listing" + ("s" if self.count != 1 else "")]
        if self.low is not None and self.low != self.median:
            parts.append(f"low {_fmt_amount(self.low)}")
        if self.high is not None and self.high != self.median and self.high != self.low:
            parts.append(f"high {_fmt_amount(self.high)}")
        if self.low_confidence:
            parts.append("few data points")
        return " · ".join(parts)

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
        high=amounts[-1],
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

    def price_item(
        self, item: Item
    ) -> tuple[list[Listing], str, str, SearchSpec | None]:
        """Return (listings, trade_site_url, summary, spec) for *item*.

        Currency is priced via the bulk exchange endpoint (no editable spec);
        everything else via the search endpoint. The returned *spec* is the
        editable search the popup lets the user refine and re-run; it is None for
        currency. The summary describes what we searched by so it's never a
        mystery.
        """
        if self._is_currency(item):
            result = self._price_currency(item)
            if result is not None:
                listings, url, summary = result
                return listings, url, summary, None
            # fall through to a normal search if the currency isn't recognised

        spec = build_search_spec(item, self.stats_index(), self._status())
        # Auto-relax the initial search: a multi-mod rare ANDs all its filters,
        # which often matches zero online listings even though a slightly looser
        # search prices it fine. Dropped filters come back disabled in the spec
        # so the popup shows them unchecked and the user can re-tighten.
        listings, url = self.search_spec(spec, relax=True)
        summary = spec.summary
        dropped = sum(1 for f in spec.stats if not f.enabled)
        if dropped:
            summary += (f"  ·  relaxed {dropped} filter"
                        f"{'s' * (dropped != 1)} to find matches")
        return listings, url, summary, spec

    def search_spec(
        self, spec: SearchSpec, *, relax: bool = False
    ) -> tuple[list[Listing], str]:
        """Run *spec* against the search endpoint; return (listings, url).

        This is the re-runnable core the popup calls each time the user edits the
        filters and presses Search — exact by default (the user's choices are
        respected). With *relax* (the initial auto-search), an empty result is
        retried with the lowest-priority stat filters progressively disabled.
        """
        listings, url = self._run_query(spec)
        if relax and not listings:
            listings, url = self._relax_search(spec, url)
        return listings, url

    def _run_query(self, spec: SearchSpec) -> tuple[list[Listing], str]:
        search = self._post_search(spec.to_query())
        result_ids = search.get("result") or []
        search_id = search.get("id")
        url = f"{SITE}/{urllib.parse.quote(self.cfg.league)}/{search_id}"
        if not result_ids:
            return [], url
        listings = self._fetch(result_ids[: self.cfg.max_listings], search_id)
        return listings, url

    def _relax_search(
        self, spec: SearchSpec, url: str
    ) -> tuple[list[Listing], str]:
        """Disable the lowest-priority stat filters until the search has matches.

        Non-pseudo mods (spirit, item rarity, …) are dropped before the pseudo
        anchors (life/ES/resistance totals) that the trade site actually prices
        on; later-rolled mods go first. At least one filter is always kept, and
        we stop early once there are enough listings to trust.
        """
        def is_pseudo(f: StatFilter) -> bool:
            return f.id.startswith("pseudo")

        order = ([f for f in reversed(spec.stats) if f.enabled and not is_pseudo(f)]
                 + [f for f in reversed(spec.stats) if f.enabled and is_pseudo(f)])

        listings: list[Listing] = []
        for filt in order[:_MAX_RELAX_DROPS]:
            if sum(1 for f in spec.stats if f.enabled) <= 1:
                break  # never drop the last filter (base-only is meaningless here)
            filt.enabled = False
            listings, url = self._run_query(spec)
            if len(listings) >= _LOW_CONFIDENCE_COUNT:
                break
        return listings, url

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
class SearchSpec:
    """The editable state of a trade2 search.

    Built automatically from an item, then handed to the popup so the user can
    toggle individual stat filters, adjust their min/max, and turn the item-level
    and rarity constraints on or off before re-running the search. ``to_query``
    renders the current state into a trade2 search body.
    """

    status: str = "online"
    name: str | None = None             # unique name match
    type: str | None = None             # base type
    term: str | None = None             # free-text last resort
    rarity: str | None = None           # type_filters rarity option, e.g. "normal"
    rarity_enabled: bool = False
    ilvl_min: int | None = None
    ilvl_enabled: bool = False
    stats: list[StatFilter] = field(default_factory=list)
    summary: str = ""

    def query_body(self) -> dict:
        q: dict = {"status": {"option": self.status}}
        if self.name:
            q["name"] = self.name
        if self.type:
            q["type"] = self.type
        if self.term and not self.type and not self.name:
            q["term"] = self.term
        type_filters: dict = {}
        if self.rarity_enabled and self.rarity:
            type_filters["rarity"] = {"option": self.rarity}
        if self.ilvl_enabled and self.ilvl_min is not None:
            type_filters["ilvl"] = {"min": self.ilvl_min}
        if type_filters:
            q["filters"] = {"type_filters": {"filters": type_filters}}
        # Include all stat rows (disabled ones carry disabled:true) so the opened
        # trade-site URL mirrors exactly what the popup shows.
        if self.stats:
            q["stats"] = [{"type": "and",
                           "filters": [f.to_query() for f in self.stats]}]
        return q

    def to_query(self) -> dict:
        return {"query": self.query_body(), "sort": {"price": "asc"}}

    @property
    def active_stat_count(self) -> int:
        return sum(1 for f in self.stats if f.enabled)


@dataclass
class SearchPlan:
    """A built search body plus a human description and the editable spec."""

    query: dict
    summary: str
    spec: SearchSpec | None = None


def build_search_spec(
    item: Item, stats_index: StatsIndex | None = None, status: str = "online"
) -> SearchSpec:
    """Build the default :class:`SearchSpec` for *item*.

    Uniques search by name (+ base type); name-searchable items by base type.
    Normal (white) bases are chance/craft fodder priced by base + item level +
    being white (no mods — chancing destroys them). Rares/magics search by base
    type **plus stat filters** from their mods (pseudo-folded, relaxed mins) when
    *stats_index* is available.
    """
    spec = SearchSpec(status=status)

    if item.rarity == "Unique" and item.name:
        spec.name = item.name
        spec.type = item.base_type or None
        spec.summary = f"by name: {item.name}"
        return spec

    if item.name_searchable and item.base_type:
        spec.type = item.base_type
        spec.summary = f"by base: {item.base_type}"
        return spec

    if item.base_type:
        spec.type = item.base_type

    # Normal (white) base: rarity=normal at >= the item's level, no stat filters.
    # Searching by base type alone (cheapest-first) returns the globally cheapest
    # base of any rarity/ilvl — a useless ~1-orb result.
    if item.rarity == "Normal" and item.base_type:
        spec.rarity = "normal"
        spec.rarity_enabled = True
        if item.item_level is not None:
            spec.ilvl_min = item.item_level
            spec.ilvl_enabled = True
        ilvl_note = f", ilvl {item.item_level}+" if item.item_level is not None else ""
        spec.summary = f"white base: {item.base_type}{ilvl_note}"
        return spec

    spec.stats = build_filter_model(item, stats_index) if stats_index else []
    if spec.stats:
        base = item.base_type or "any base"
        n = len(spec.stats)
        spec.summary = f"{base} + {n} stat filter{'s' * (n != 1)}"
    elif item.base_type:
        spec.summary = "base only — no mods matched the catalog"
    elif item.name:
        spec.term = item.name  # last resort when we have nothing else
        spec.summary = f"by text: {item.name}"
    else:
        spec.summary = "everything (could not identify item)"
    return spec


def plan_search(
    item: Item, stats_index: StatsIndex | None = None, status: str = "online"
) -> SearchPlan:
    """Plan a trade2 search for *item* (query body + summary + editable spec)."""
    spec = build_search_spec(item, stats_index, status)
    return SearchPlan(spec.to_query(), spec.summary, spec)


def build_query(item: Item, stats_index: StatsIndex | None = None) -> dict:
    """Backward-compatible helper returning just the query body."""
    return plan_search(item, stats_index).query


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
        if not want_amount or have_amount is None:
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
