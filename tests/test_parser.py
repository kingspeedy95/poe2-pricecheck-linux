"""Tests for the item parser, using real clipboard captures as fixtures."""

from pathlib import Path

import pytest

from poe2price.parser import normalize_stat, parse

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> str:
    return (FIXTURES / name).read_text()


def test_normalize_stat_advanced_roll():
    text, values = normalize_stat("4(4-8)% increased Effect of your Mark Skills")
    assert text == "#% increased Effect of your Mark Skills"
    assert values == [4.0]


def test_normalize_stat_plain_number():
    text, values = normalize_stat("+1 to Level of all Minion Skills")
    assert text == "+# to Level of all Minion Skills"
    assert values == [1.0]


def test_normalize_stat_signed_roll():
    text, values = normalize_stat("+12(10-14) to maximum Mana")
    assert text == "+# to maximum Mana"
    assert values == [12.0]


def test_parse_jewel_header():
    item = parse(_load("jewel_magic.txt"))
    assert item.item_class == "Jewels"
    assert item.rarity == "Magic"
    assert item.name == "Marking Emerald of Hunting"
    assert item.item_level == 24


def test_parse_jewel_mods():
    item = parse(_load("jewel_magic.txt"))
    assert len(item.explicits) == 2

    prefix, suffix = item.explicits
    assert prefix.text == "#% increased Effect of your Mark Skills"
    assert prefix.values == [4.0]
    assert prefix.affix == "prefix"
    assert prefix.tier == 1
    assert prefix.name == "Marking"

    assert suffix.text == "#% increased Critical Damage Bonus with Spears"
    assert suffix.values == [17.0]
    assert suffix.affix == "suffix"


def test_parse_sceptre_properties_and_requirements():
    item = parse(_load("sceptre_magic.txt"))
    assert item.item_class == "Sceptres"
    assert item.rarity == "Magic"
    assert item.item_level == 3
    assert item.properties.get("Spirit") == "100"
    assert item.requirements == {"Level": 3, "Int": 9}


def test_parse_sceptre_mods():
    item = parse(_load("sceptre_magic.txt"))
    texts = [(m.text, m.values, m.affix) for m in item.explicits]
    assert ("+# to maximum Mana", [12.0], "prefix") in texts
    assert ("+# to Level of all Minion Skills", [1.0], "suffix") in texts


def test_flavour_text_is_not_a_modifier():
    item = parse(_load("jewel_magic.txt"))
    joined = " ".join(m.raw for m in item.explicits)
    assert "Place into an allocated" not in joined


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
