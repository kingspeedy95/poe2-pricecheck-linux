"""Tests for external reference link building."""

from poe2price.links import lookup_term, poe2db_url, wiki_url
from poe2price.parser import Item


def test_lookup_term_prefers_unique_name():
    item = Item(rarity="Unique", name="Astramentis", base_type="Stellar Amulet")
    assert lookup_term(item) == "Astramentis"


def test_lookup_term_uses_base_for_non_unique():
    item = Item(rarity="Rare", name="Doom Coil", base_type="Iron Ring")
    assert lookup_term(item) == "Iron Ring"


def test_lookup_term_none_when_empty():
    assert lookup_term(Item()) is None


def test_poe2db_url_slugs_spaces():
    item = Item(rarity="Currency", base_type="Stellar Amulet", name="Stellar Amulet")
    assert poe2db_url(item) == "https://poe2db.tw/us/Stellar_Amulet"


def test_wiki_url_for_unique():
    item = Item(rarity="Unique", name="Astramentis")
    assert wiki_url(item) == "https://www.poewiki.net/wiki/Astramentis"


def test_urls_none_for_unidentifiable_item():
    assert poe2db_url(Item()) is None
    assert wiki_url(Item()) is None
