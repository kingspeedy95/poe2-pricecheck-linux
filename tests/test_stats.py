"""Tests for stat-ID matching and stat-based query building."""

import json
from pathlib import Path

import poe2price.stats as stats_mod
from poe2price.parser import Item, Modifier, parse
from poe2price.stats import StatsIndex, canon, load_stats_index
from poe2price.trade import build_query

FIXTURES = Path(__file__).parent / "fixtures"

# A tiny hand-built catalog mirroring the real schema for fast unit tests.
# No Pseudo group here, so resistance/life mods stay as individual filters.
CATALOG = {
    "result": [
        {"label": "Explicit", "entries": [
            {"id": "explicit.stat_life", "text": "# to maximum Life", "type": "explicit"},
            {"id": "explicit.stat_fireres", "text": "#% to Fire Resistance", "type": "explicit"},
            {"id": "explicit.stat_phys", "text": "Adds # to # Physical Damage", "type": "explicit"},
            {"id": "explicit.stat_spell", "text": "#% increased Spell Damage", "type": "explicit"},
        ]},
        {"label": "Implicit", "entries": [
            {"id": "implicit.stat_life", "text": "# to maximum Life", "type": "implicit"},
        ]},
        {"label": "Augment", "entries": [
            {"id": "rune.stat_fireres", "text": "#% to Fire Resistance", "type": "augment"},
        ]},
    ]
}

# Catalog including the pseudo totals, for folding tests.
PSEUDO_CATALOG = {
    "result": CATALOG["result"] + [
        {"label": "Pseudo", "entries": [
            {"id": "pseudo.elem", "text": "+#% total Elemental Resistance", "type": "pseudo"},
            {"id": "pseudo.life", "text": "+# total maximum Life", "type": "pseudo"},
        ]},
        {"label": "ExplicitCold", "entries": [
            {"id": "explicit.stat_coldres", "text": "#% to Cold Resistance", "type": "explicit"},
        ]},
    ]
}


def _mod(text, values, kind="explicit"):
    return Modifier(text=text, values=values, kind=kind)


# --- canon ------------------------------------------------------------------

def test_canon_collapses_plus_hash():
    assert canon("+# to maximum Life") == "# to maximum Life"
    assert canon("#% increased Damage") == "#% increased Damage"


# --- StatsIndex.match -------------------------------------------------------

def test_match_explicit():
    idx = StatsIndex(CATALOG)
    assert idx.match(_mod("+# to maximum Life", [50])) == "explicit.stat_life"


def test_match_picks_type_by_kind():
    idx = StatsIndex(CATALOG)
    assert idx.match(_mod("+# to maximum Life", [50], "implicit")) == "implicit.stat_life"


def test_match_rune_uses_augment_id():
    idx = StatsIndex(CATALOG)
    assert idx.match(_mod("+#% to Fire Resistance", [30], "rune")) == "rune.stat_fireres"


def test_match_unknown_returns_none():
    idx = StatsIndex(CATALOG)
    assert idx.match(_mod("#% chance to explode", [5])) is None


# --- build_query with stats -------------------------------------------------

def test_rare_query_includes_stat_filters_with_relaxed_min():
    idx = StatsIndex(CATALOG)  # no pseudo group -> individual filters
    item = Item(rarity="Rare", name="Doom Coil", base_type="Iron Ring",
                explicits=[_mod("+# to maximum Life", [50]),
                           _mod("+#% to Fire Resistance", [30])])
    q = build_query(item, idx)
    assert q["query"]["type"] == "Iron Ring"
    filters = q["query"]["stats"][0]["filters"]
    ids = [f["id"] for f in filters]
    assert ids == ["explicit.stat_life", "explicit.stat_fireres"]
    # Mins are relaxed to 90% (floored): 50->45, 30->27.
    assert filters[0]["value"] == {"min": 45}
    assert filters[1]["value"] == {"min": 27}


def test_pseudo_folds_resistances_into_total():
    idx = StatsIndex(PSEUDO_CATALOG)
    item = Item(rarity="Rare", base_type="Iron Ring",
                explicits=[_mod("+#% to Fire Resistance", [30]),
                           _mod("+#% to Cold Resistance", [20])])
    q = build_query(item, idx)
    filters = q["query"]["stats"][0]["filters"]
    ids = [f["id"] for f in filters]
    # The two resists collapse into one pseudo total (50 -> relaxed 45).
    assert ids == ["pseudo.elem"]
    assert filters[0]["value"] == {"min": 45}


def test_pseudo_keeps_non_folded_mods():
    idx = StatsIndex(PSEUDO_CATALOG)
    item = Item(rarity="Rare", base_type="Wand",
                explicits=[_mod("+#% to Fire Resistance", [40]),
                           _mod("#% increased Spell Damage", [60])])
    q = build_query(item, idx)
    ids = [f["id"] for f in q["query"]["stats"][0]["filters"]]
    assert "pseudo.elem" in ids          # resist folded
    assert "explicit.stat_spell" in ids  # spell damage kept individually


def test_multi_value_mod_has_no_min():
    idx = StatsIndex(CATALOG)
    item = Item(rarity="Rare", base_type="Bow",
                explicits=[_mod("Adds # to # Physical Damage", [1, 5])])
    q = build_query(item, idx)
    f = q["query"]["stats"][0]["filters"][0]
    assert f["id"] == "explicit.stat_phys"
    assert "value" not in f  # ranged mods match any roll


def test_magic_without_base_is_stats_only():
    idx = StatsIndex(CATALOG)
    item = Item(rarity="Magic", name="X", base_type=None,
                explicits=[_mod("+# to maximum Life", [40])])
    q = build_query(item, idx)
    assert "type" not in q["query"]
    assert q["query"]["stats"][0]["filters"][0]["id"] == "explicit.stat_life"


def test_no_index_falls_back_to_base_only():
    item = Item(rarity="Rare", base_type="Iron Ring",
                explicits=[_mod("+# to maximum Life", [50])])
    q = build_query(item, None)
    assert q["query"]["type"] == "Iron Ring"
    assert "stats" not in q["query"]


def test_unmatched_mods_drop_out_but_query_still_built():
    idx = StatsIndex(CATALOG)
    item = Item(rarity="Rare", base_type="Iron Ring",
                explicits=[_mod("#% chance to explode", [5])])  # not in catalog
    q = build_query(item, idx)
    assert q["query"]["type"] == "Iron Ring"
    assert "stats" not in q["query"]  # nothing matched


# --- against the real catalog fixture ---------------------------------------

def test_real_catalog_matches_parsed_fixtures():
    data = json.loads((FIXTURES / "api_data_stats.json").read_text())
    idx = StatsIndex(data)
    item = parse((FIXTURES / "sceptre_magic.txt").read_text())
    matched = [idx.match(m) for m in item.explicits]
    assert matched == ["explicit.stat_1050105434", "explicit.stat_2162097452"]


# --- caching ----------------------------------------------------------------

class _FakeSession:
    def __init__(self, data):
        self._data = data
        self.calls = 0

    def get(self, url, timeout=None):
        self.calls += 1
        return _FakeResp(self._data)


class _FakeResp:
    def __init__(self, data):
        self._data = data

    def raise_for_status(self):
        pass

    def json(self):
        return self._data


def test_load_fetches_and_caches(tmp_path, monkeypatch):
    cache = tmp_path / "stats.json"
    monkeypatch.setattr(stats_mod, "_CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(stats_mod, "_CACHE_PATH", str(cache))
    session = _FakeSession(CATALOG)

    idx = load_stats_index(session)
    assert session.calls == 1
    assert cache.exists()
    assert len(idx) > 0

    # Second load uses the fresh cache — no new network call.
    session2 = _FakeSession(CATALOG)
    load_stats_index(session2)
    assert session2.calls == 0
