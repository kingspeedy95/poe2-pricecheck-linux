"""Tests for trade query building and POESESSID validation (no network)."""

import json
from pathlib import Path

import pytest

from poe2price.config import Config
from poe2price.parser import Item
from poe2price.stats import StatFilter
from poe2price.trade import (
    Listing,
    SearchSpec,
    TradeClient,
    TradeError,
    _exchange_listings,
    _to_listing,
    build_query,
    build_search_spec,
    plan_search,
    summarize,
)

FIXTURES = Path(__file__).parent / "fixtures"


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict | None = None,
                 headers: dict | None = None, text: str = ""):
        self.status_code = status_code
        self._payload = payload or {}
        self.headers: dict = headers or {}
        self.text = text

    @property
    def ok(self) -> bool:
        return 200 <= self.status_code < 300

    def json(self):
        return self._payload


def _client(poesessid: str = "") -> TradeClient:
    # Config() builds defaults without touching disk (only load() saves).
    return TradeClient(Config(poesessid=poesessid))


def test_check_session_without_cookie():
    ok, msg = _client("").check_session()
    assert ok is False
    assert "no POESESSID" in msg


def test_check_session_authenticated(monkeypatch):
    client = _client("abc")
    monkeypatch.setattr(
        client.session, "get",
        lambda *a, **k: _FakeResponse(200, {"name": "kingspeedy"}),
    )
    ok, msg = client.check_session()
    assert ok is True
    assert "kingspeedy" in msg


def test_check_session_rejected(monkeypatch):
    client = _client("abc")
    monkeypatch.setattr(
        client.session, "get", lambda *a, **k: _FakeResponse(403)
    )
    ok, msg = client.check_session()
    assert ok is False
    assert "rejected" in msg


def test_build_query_unique():
    q = build_query(Item(rarity="Unique", name="Headhunter", base_type="Leather Belt"))
    assert q["query"]["name"] == "Headhunter"
    assert q["query"]["type"] == "Leather Belt"
    assert q["sort"] == {"price": "asc"}


def test_build_query_currency_by_type():
    q = build_query(Item(rarity="Currency", item_class="Stackable Currency",
                         base_type="Exalted Orb"))
    assert q["query"]["type"] == "Exalted Orb"
    assert "name" not in q["query"]


# --- Regression against real captured trade2 responses (see PROGRESS.md) ----
# These fixtures were captured live on 2026-06-06 (league "Runes of Aldur") and
# pin the fetch/listing schema so a future API change is caught by the suite.

def test_build_query_gem_by_type():
    q = build_query(Item(rarity="Currency", item_class="Skill Gems",
                         base_type="Fireball"))
    assert q["query"]["type"] == "Fireball"


def test_build_query_falls_back_to_name():
    # A rare with no base type and no searchable class -> free-text term.
    q = build_query(Item(rarity="Rare", name="Doom Whisper"))
    assert q["query"].get("term") == "Doom Whisper"


# --- Listing.price_text -----------------------------------------------------

def test_price_text_whole_number():
    assert Listing(5.0, "exalted", "a", "@a").price_text == "5 exalted"


def test_price_text_fractional():
    assert Listing(2.5, "divine", "a", "@a").price_text == "2.5 divine"


def test_price_text_no_amount():
    assert Listing(None, None, "a", "@a").price_text == "no price"


# --- HTTP error handling ----------------------------------------------------

def test_raise_for_status_rate_limited():
    client = _client()
    with pytest.raises(TradeError, match="Rate limited"):
        client._raise_for_status(_FakeResponse(429, headers={"Retry-After": "12"}))


def test_raise_for_status_unauthorised():
    client = _client()
    with pytest.raises(TradeError, match="POESESSID"):
        client._raise_for_status(_FakeResponse(403))


def test_raise_for_status_server_error():
    client = _client()
    with pytest.raises(TradeError, match="server error"):
        client._raise_for_status(_FakeResponse(500, text="boom"))


def test_raise_for_status_ok_passes():
    client = _client()
    client._raise_for_status(_FakeResponse(200))  # must not raise


def test_learn_throttle_no_spacing_with_headroom():
    client = _client()
    # Plenty of headroom (1 of 3, 1 of 8) -> run at full speed, no spacing.
    client._learn_throttle("search", _FakeResponse(200, headers={
        "X-Rate-Limit-Account": "3:5:60",
        "X-Rate-Limit-Account-State": "1:5:0",
        "X-Rate-Limit-Ip": "8:10:60",
        "X-Rate-Limit-Ip-State": "1:10:0",
    }))
    assert client._throttle["search"][0] == 0.0


def test_learn_throttle_spaces_near_ceiling():
    client = _client()
    # Account at 2 of 3 (one below ceiling) -> sustainable rate 5/3s.
    client._learn_throttle("search", _FakeResponse(200, headers={
        "X-Rate-Limit-Account": "3:5:60",
        "X-Rate-Limit-Account-State": "2:5:0",
        "X-Rate-Limit-Ip": "8:10:60",
        "X-Rate-Limit-Ip-State": "1:10:0",
    }))
    assert abs(client._throttle["search"][0] - (5 / 3)) < 0.01


def test_learn_throttle_capped():
    client = _client()
    # 1 per 300s, already used -> 300s sustainable, capped to _MAX_SPACING.
    client._learn_throttle("search", _FakeResponse(200, headers={
        "X-Rate-Limit-Ip": "1:300:1800",
        "X-Rate-Limit-Ip-State": "1:300:0",
    }))
    assert client._throttle["search"][0] == 6.0


def test_await_throttle_no_state_does_not_block(monkeypatch):
    import poe2price.trade as trade_mod
    slept = []
    monkeypatch.setattr(trade_mod.time, "sleep", lambda s: slept.append(s))
    _client()._await_throttle("search")  # nothing learned yet
    assert slept == []


def test_endpoint_label():
    c = _client()
    assert c._endpoint_label("https://x/api/trade2/search/poe2/L") == "search"
    assert c._endpoint_label("https://x/api/trade2/fetch/a,b") == "fetch"
    assert c._endpoint_label("https://x/api/trade2/exchange/L") == "exchange"


def test_retry_after_prefers_header():
    assert TradeClient._retry_after_seconds(
        _FakeResponse(429, headers={"Retry-After": "7"})) == 7.0


def test_retry_after_falls_back_to_state():
    # No Retry-After; read the active restriction (third field) from state.
    wait = TradeClient._retry_after_seconds(_FakeResponse(429, headers={
        "X-Rate-Limit-Ip-State": "8:10:0,15:60:45",
    }))
    assert wait == 45.0


def test_send_auto_waits_short_429(monkeypatch):
    _no_sleep(monkeypatch)
    client = _client()
    calls = []

    def fake_request(method, url, **kwargs):
        calls.append(method)
        if len(calls) == 1:
            return _FakeResponse(429, headers={"Retry-After": "3"})
        return _FakeResponse(200, {"ok": True})

    monkeypatch.setattr(client.session, "request", fake_request)
    resp = client._send("GET", "http://x/fetch/a")
    assert resp.status_code == 200
    assert len(calls) == 2  # waited out the short ban and retried


def test_send_surfaces_long_429(monkeypatch):
    _no_sleep(monkeypatch)
    client = _client()
    monkeypatch.setattr(client.session, "request",
                        lambda *a, **k: _FakeResponse(429, headers={"Retry-After": "60"}))
    with pytest.raises(TradeError, match="about 60s"):
        client._send("GET", "http://x/search/poe2/L")


# --- price_item flow (mocked HTTP) ------------------------------------------

def test_price_item_returns_listings_url_summary_and_spec(monkeypatch):
    client = _client()
    monkeypatch.setattr(client, "_post_search",
                        lambda q: {"id": "SID", "result": ["a", "b"]})
    monkeypatch.setattr(client, "_fetch",
                        lambda ids, sid: [Listing(1, "exalted", "x", "@x")])
    listings, url, summary, spec = client.price_item(Item(rarity="Unique", name="X"))
    assert len(listings) == 1
    assert url.endswith("/SID")
    assert summary == "by name: X"
    assert spec is not None and spec.name == "X"  # editable spec returned


def test_price_item_no_results(monkeypatch):
    client = _client()
    monkeypatch.setattr(client, "_post_search",
                        lambda q: {"id": "SID", "result": []})
    listings, url, summary, spec = client.price_item(Item(rarity="Unique", name="X"))
    assert listings == []
    assert "SID" in url


def test_price_item_currency_has_no_spec(monkeypatch):
    client = _client()
    monkeypatch.setattr(client, "currency_map", lambda: {"Divine Orb": "divine"})
    monkeypatch.setattr(client, "_send",
                        lambda *a, **k: _FakeResponse(200, {"id": "X", "result": {}}))
    listings, url, summary, spec = client.price_item(
        Item(rarity="Currency", base_type="Divine Orb"))
    assert spec is None  # currency isn't refinable by stat filters


# --- transient 5xx retry ----------------------------------------------------

def _no_sleep(monkeypatch):
    import poe2price.trade as trade_mod
    monkeypatch.setattr(trade_mod.time, "sleep", lambda s: None)


def test_send_retries_500_then_succeeds(monkeypatch):
    _no_sleep(monkeypatch)
    client = _client()
    calls = []

    def fake_request(method, url, **kwargs):
        calls.append(method)
        # First call 500, second call 200.
        return _FakeResponse(500 if len(calls) == 1 else 200, {"ok": True})

    monkeypatch.setattr(client.session, "request", fake_request)
    resp = client._send("POST", "http://x", json={})
    assert resp.status_code == 200
    assert len(calls) == 2  # retried once


def test_send_gives_up_after_max_attempts(monkeypatch):
    _no_sleep(monkeypatch)
    client = _client()
    calls = []

    def fake_request(method, url, **kwargs):
        calls.append(method)
        return _FakeResponse(503, text="busy")

    monkeypatch.setattr(client.session, "request", fake_request)
    with pytest.raises(TradeError, match="server error"):
        client._send("GET", "http://x")
    assert len(calls) == 3  # _MAX_ATTEMPTS


def test_send_retries_network_error(monkeypatch):
    import requests as requests_mod
    _no_sleep(monkeypatch)
    client = _client()
    calls = []

    def fake_request(method, url, **kwargs):
        calls.append(method)
        if len(calls) < 2:
            raise requests_mod.ConnectionError("boom")
        return _FakeResponse(200, {"ok": True})

    monkeypatch.setattr(client.session, "request", fake_request)
    resp = client._send("GET", "http://x")
    assert resp.status_code == 200
    assert len(calls) == 2


def test_send_does_not_retry_403(monkeypatch):
    _no_sleep(monkeypatch)
    client = _client()
    calls = []

    def fake_request(method, url, **kwargs):
        calls.append(method)
        return _FakeResponse(403)

    monkeypatch.setattr(client.session, "request", fake_request)
    with pytest.raises(TradeError, match="POESESSID"):
        client._send("GET", "http://x")
    assert len(calls) == 1  # auth errors are not retried


# --- price summary ----------------------------------------------------------

def test_summarize_empty():
    s = summarize([])
    assert s.count == 0 and s.median is None
    assert s.text == "no price data"


def test_summary_headline_and_detail():
    listings = [Listing(i, "exalted", "a", "@a") for i in (40, 50, 60, 80)]
    s = summarize(listings)
    assert s.headline == "~55 exalted"          # median of 40,50,60,80
    assert "4 listings" in s.detail
    assert "low 40" in s.detail


def test_summary_headline_no_data():
    assert summarize([]).headline == "no price data"
    assert summarize([]).detail == ""


def test_summarize_low_confidence_flag():
    s = summarize([Listing(5, "exalted", "a", "@a"), Listing(7, "exalted", "b", "@b")])
    assert s.low_confidence is True
    assert "few data points" in s.text


def test_summarize_confident_with_enough_listings():
    listings = [Listing(i, "exalted", "a", "@a") for i in (4, 5, 6, 7)]
    s = summarize(listings)
    assert s.low_confidence is False
    assert "few data points" not in s.text


def test_summarize_reports_spread_high():
    # A flooded white-base market: cheap floor, expensive outliers. The detail
    # surfaces the high so a user eyeballing pricey in-game listings sees them
    # without the median being dragged up by the outliers.
    listings = [Listing(p, "exalted", "a", "@a") for p in (3, 3, 5, 7, 10, 50)]
    s = summarize(listings)
    assert s.high == 50
    assert "low 3" in s.detail and "high 50" in s.detail


def test_summarize_no_spread_when_all_equal():
    s = summarize([Listing(1, "exalted", "a", "@a") for _ in range(5)])
    assert s.low == s.median == s.high == 1
    assert "low" not in s.detail and "high" not in s.detail  # nothing to show


def test_summarize_uses_dominant_currency_and_median():
    listings = [
        Listing(1, "exalted", "a", "@a"),    # lowball outlier
        Listing(40, "exalted", "b", "@b"),
        Listing(50, "exalted", "c", "@c"),
        Listing(60, "exalted", "d", "@d"),
        Listing(2, "divine", "e", "@e"),     # different currency, ignored
    ]
    s = summarize(listings)
    assert s.currency == "exalted"
    assert s.count == 4
    assert s.low == 1
    assert s.median == 45  # median(1,40,50,60) -> (40+50)/2, robust to lowball
    assert "exalted" in s.text


# --- search summary / planning ----------------------------------------------

def test_plan_summary_base_only_when_no_mods_match():
    # Rare with a mod not in any catalog -> base-only, and the summary says so.
    plan = plan_search(Item(rarity="Rare", base_type="Iron Ring"), None)
    assert "base only" in plan.summary
    assert "stats" not in plan.query["query"]


def test_plan_white_base_filters_rarity_and_ilvl():
    # A Normal (white) base is gambling/crafting fodder: it must be searched as
    # rarity=normal at >= its item level, not by base type alone (which returns
    # the globally cheapest base of any rarity — a useless ~1-orb result).
    plan = plan_search(
        Item(rarity="Normal", base_type="Utility Belt", item_level=82), None
    )
    tf = plan.query["query"]["filters"]["type_filters"]["filters"]
    assert tf["rarity"] == {"option": "normal"}
    assert tf["ilvl"] == {"min": 82}
    assert plan.query["query"]["type"] == "Utility Belt"
    assert "white base" in plan.summary and "82+" in plan.summary


def test_plan_white_base_without_item_level_still_constrains_rarity():
    plan = plan_search(Item(rarity="Normal", base_type="Utility Belt"), None)
    tf = plan.query["query"]["filters"]["type_filters"]["filters"]
    assert tf == {"rarity": {"option": "normal"}}  # no ilvl when unknown


# --- SearchSpec (editable search model) -------------------------------------

def test_spec_to_query_includes_disabled_stats():
    spec = SearchSpec(type="Sapphire Ring", stats=[
        StatFilter(id="explicit.stat_life", label="+# to maximum Life", min=80),
        StatFilter(id="explicit.stat_cold", label="+#% Cold Res", enabled=False, min=30),
    ])
    q = spec.to_query()["query"]
    filters = q["stats"][0]["filters"]
    assert filters[0] == {"id": "explicit.stat_life", "disabled": False,
                          "value": {"min": 80}}
    # Disabled rows ride along with disabled:true so the trade URL mirrors the UI.
    assert filters[1]["disabled"] is True
    assert spec.active_stat_count == 1


def test_spec_to_query_type_filters_only_when_enabled():
    spec = SearchSpec(type="Utility Belt", rarity="normal", rarity_enabled=True,
                      ilvl_min=82, ilvl_enabled=False)
    tf = spec.to_query()["query"]["filters"]["type_filters"]["filters"]
    assert tf == {"rarity": {"option": "normal"}}  # ilvl disabled -> omitted


def test_build_search_spec_white_base():
    spec = build_search_spec(Item(rarity="Normal", base_type="Utility Belt",
                                  item_level=82), None)
    assert spec.rarity_enabled and spec.ilvl_enabled and spec.ilvl_min == 82
    assert spec.stats == []  # white bases carry no editable mods


def test_search_spec_method_runs_and_returns_url(monkeypatch):
    client = _client()
    monkeypatch.setattr(client, "_post_search",
                        lambda q: {"id": "SID", "result": ["a"]})
    monkeypatch.setattr(client, "_fetch",
                        lambda ids, sid: [Listing(2, "exalted", "x", "@x")])
    listings, url = client.search_spec(SearchSpec(type="X"))
    assert len(listings) == 1 and url.endswith("/SID")


def test_plan_summary_by_name_for_unique():
    plan = plan_search(Item(rarity="Unique", name="Astramentis"), None)
    assert plan.summary == "by name: Astramentis"


def test_plan_status_defaults_online():
    plan = plan_search(Item(rarity="Unique", name="X"), None)
    assert plan.query["query"]["status"]["option"] == "online"


def test_plan_status_any():
    plan = plan_search(Item(rarity="Unique", name="X"), None, status="any")
    assert plan.query["query"]["status"]["option"] == "any"


def test_client_status_validation():
    assert TradeClient(Config(status="any"))._status() == "any"
    assert TradeClient(Config(status="online"))._status() == "online"
    assert TradeClient(Config(status="garbage"))._status() == "online"


# --- currency dispatch / exchange parsing -----------------------------------

def test_is_currency():
    assert TradeClient._is_currency(Item(rarity="Currency", base_type="Divine Orb"))
    assert TradeClient._is_currency(
        Item(item_class="Stackable Currency", base_type="Exalted Orb"))
    assert not TradeClient._is_currency(Item(rarity="Unique", name="X"))


def test_exchange_listings_compute_unit_price():
    data = {"result": {
        "a": {"listing": {
            "account": {"name": "seller#1"},
            "whisper": "@seller hi",
            "offers": [{
                "exchange": {"currency": "exalted", "amount": 20},
                "item": {"currency": "divine", "amount": 2},
            }],
        }},
    }}
    listings = _exchange_listings(data, limit=10)
    assert len(listings) == 1
    # 20 exalted for 2 divine -> 10 exalted per divine.
    assert listings[0].amount == 10
    assert listings[0].currency == "exalted"
    assert listings[0].account == "seller#1"


def test_exchange_listings_respects_limit_and_skips_bad():
    data = {"result": {
        "a": {"listing": {"offers": [{"exchange": {"currency": "exalted", "amount": 5},
                                      "item": {"currency": "x", "amount": 0}}]}},  # bad: 0
        "missing_have": {"listing": {"offers": [{"exchange": {"currency": "exalted"},
                                      "item": {"currency": "x", "amount": 2}}]}},  # no have amount
        "b": {"listing": {"offers": [{"exchange": {"currency": "exalted", "amount": 6},
                                      "item": {"currency": "x", "amount": 3}}]}},
    }}
    listings = _exchange_listings(data, limit=10)
    assert [x.amount for x in listings] == [2.0]  # zero- and missing-amount entries skipped


@pytest.mark.parametrize("fixture", [
    "api_fetch_unique_astramentis.json",
    "api_fetch_currency_divine.json",
])
def test_to_listing_parses_real_fetch(fixture):
    data = json.loads((FIXTURES / fixture).read_text())
    results = data["result"]
    assert results, "fixture should contain listings"
    for entry in results:
        listing = _to_listing(entry)
        # Every real listing carries a price and a whisper string.
        assert listing.amount is not None
        assert listing.currency
        assert listing.whisper
        assert listing.account
        # price_text renders without raising and includes the currency.
        assert listing.currency in listing.price_text
