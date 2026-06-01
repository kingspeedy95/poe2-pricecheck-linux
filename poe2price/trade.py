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

import time
import urllib.parse
from dataclasses import dataclass

import requests

from .parser import Item

API = "https://www.pathofexile.com/api/trade2"
SITE = "https://www.pathofexile.com/trade2/search/poe2"


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
        amt = int(self.amount) if self.amount == int(self.amount) else self.amount
        return f"{amt} {self.currency or ''}".strip()


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

    # -- public API ---------------------------------------------------------

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

    def price_item(self, item: Item) -> tuple[list[Listing], str]:
        """Return (listings, trade_site_url) for *item*."""
        query = build_query(item)
        search = self._post_search(query)
        result_ids = search.get("result") or []
        search_id = search.get("id")
        url = f"{SITE}/{urllib.parse.quote(self.cfg.league)}/{search_id}"
        if not result_ids:
            return [], url
        listings = self._fetch(result_ids[: self.cfg.max_listings], search_id)
        return listings, url

    # -- HTTP ---------------------------------------------------------------

    def _post_search(self, query: dict) -> dict:
        url = f"{API}/search/poe2/{urllib.parse.quote(self.cfg.league)}"
        resp = self.session.post(url, json=query, timeout=15)
        self._raise_for_status(resp)
        self._respect_rate_limit(resp)
        return resp.json()

    def _fetch(self, ids: list[str], search_id: str) -> list[Listing]:
        listings: list[Listing] = []
        for start in range(0, len(ids), 10):
            batch = ids[start : start + 10]
            url = f"{API}/fetch/{','.join(batch)}"
            resp = self.session.get(url, params={"query": search_id}, timeout=15)
            self._raise_for_status(resp)
            for entry in resp.json().get("result") or []:
                listings.append(_to_listing(entry))
            self._respect_rate_limit(resp)
        return listings

    def _raise_for_status(self, resp: requests.Response) -> None:
        if resp.status_code == 429:
            retry = resp.headers.get("Retry-After", "a few")
            raise TradeError(f"Rate limited by the trade API. Retry after {retry}s.")
        if resp.status_code in (401, 403):
            raise TradeError(
                "Blocked by Cloudflare / not authorised. "
                "Set a fresh POESESSID in the config."
            )
        if not resp.ok:
            raise TradeError(f"Trade API error {resp.status_code}: {resp.text[:200]}")

    def _respect_rate_limit(self, resp: requests.Response) -> None:
        """Back off if we're close to a rate-limit bucket's ceiling."""
        rules = resp.headers.get("X-Rate-Limit-Ip")
        state = resp.headers.get("X-Rate-Limit-Ip-State")
        sleep = 0.4
        if rules and state:
            try:
                # Each is "hits:period:restrict, ..."; compare current to max.
                for limit, cur in zip(rules.split(","), state.split(",")):
                    max_hits = int(limit.split(":")[0])
                    used = int(cur.split(":")[0])
                    if used >= max_hits - 1:
                        sleep = max(sleep, float(cur.split(":")[1]))
            except (ValueError, IndexError):
                pass
        time.sleep(sleep)


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


def build_query(item: Item) -> dict:
    """Build a trade2 search body for *item*.

    Phase 1: name/base searches. Uniques search by name (+ base type);
    currency/gems/waystones by base type. Rares/magics fall back to a base
    or free-text search until stat filters land in phase 2.
    """
    query: dict = {"status": {"option": "online"}}

    if item.rarity == "Unique" and item.name:
        query["name"] = item.name
        if item.base_type:
            query["type"] = item.base_type
    elif item.name_searchable and item.base_type:
        query["type"] = item.base_type
    elif item.base_type:
        query["type"] = item.base_type
    elif item.name:
        query["term"] = item.name

    return {"query": query, "sort": {"price": "asc"}}
