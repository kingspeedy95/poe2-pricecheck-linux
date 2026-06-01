"""Tests for trade query building and POESESSID validation (no network)."""

from poe2price.config import Config
from poe2price.parser import Item
from poe2price.trade import TradeClient, build_query


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict | None = None):
        self.status_code = status_code
        self._payload = payload or {}
        self.headers: dict = {}

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
