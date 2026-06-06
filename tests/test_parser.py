"""Tests for the item parser, using real clipboard captures as fixtures."""

from pathlib import Path

import pytest

from poe2price.parser import Item, Modifier, normalize_stat, parse

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> str:
    return (FIXTURES / name).read_text()


# --- Item dataclass properties ----------------------------------------------

def test_display_name_combines_name_and_base():
    item = Item(name="Astramentis", base_type="Stellar Amulet")
    assert item.display_name == "Astramentis (Stellar Amulet)"


def test_display_name_when_name_equals_base():
    item = Item(name="Divine Orb", base_type="Divine Orb")
    assert item.display_name == "Divine Orb"


def test_display_name_unknown():
    assert Item().display_name == "Unknown item"


def test_name_searchable_unique_and_currency():
    assert Item(rarity="Unique", name="X").name_searchable is True
    assert Item(rarity="Currency").name_searchable is True


def test_name_searchable_by_item_class():
    assert Item(rarity="Normal", item_class="Skill Gems").name_searchable is True
    assert Item(rarity="Rare", item_class="Body Armours").name_searchable is False


def test_normalize_stat_advanced_roll():
    text, values, ranges = normalize_stat("4(4-8)% increased Effect of your Mark Skills")
    assert text == "#% increased Effect of your Mark Skills"
    assert values == [4.0]
    assert ranges == [(4.0, 8.0)]


def test_normalize_stat_plain_number():
    text, values, ranges = normalize_stat("+1 to Level of all Minion Skills")
    assert text == "+# to Level of all Minion Skills"
    assert values == [1.0]
    assert ranges == [None]


def test_normalize_stat_signed_roll():
    text, values, ranges = normalize_stat("+12(10-14) to maximum Mana")
    assert text == "+# to maximum Mana"
    assert values == [12.0]
    assert ranges == [(10.0, 14.0)]


def test_roll_quality():
    # 4 on a 4-8 range -> 0.0 (worst), 8 -> 1.0, 6 -> 0.5.
    assert Modifier(text="#", values=[4.0], ranges=[(4.0, 8.0)]).roll_quality == 0.0
    assert Modifier(text="#", values=[8.0], ranges=[(4.0, 8.0)]).roll_quality == 1.0
    assert Modifier(text="#", values=[6.0], ranges=[(4.0, 8.0)]).roll_quality == 0.5


def test_roll_quality_none_without_range():
    assert Modifier(text="#", values=[5.0], ranges=[None]).roll_quality is None
    assert Modifier(text="#", values=[], ranges=[]).roll_quality is None


def test_parsed_mod_has_ranges():
    item = parse(_load("jewel_magic.txt"))
    prefix = item.explicits[0]
    # "4(4-8)%..." -> value 4 in range (4,8) -> quality 0.0
    assert prefix.ranges == [(4.0, 8.0)]
    assert prefix.roll_quality == 0.0


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


# --- parse() header handling across rarities --------------------------------

def test_parse_unique_name_and_base():
    text = (
        "Item Class: Amulets\n"
        "Rarity: Unique\n"
        "Astramentis\n"
        "Stellar Amulet\n"
        "--------\n"
        "Item Level: 80\n"
    )
    item = parse(text)
    assert item.rarity == "Unique"
    assert item.name == "Astramentis"
    assert item.base_type == "Stellar Amulet"
    assert item.item_level == 80


def test_parse_currency_uses_base_as_name():
    text = (
        "Item Class: Stackable Currency\n"
        "Rarity: Currency\n"
        "Divine Orb\n"
        "--------\n"
        "Stack Size: 7/10\n"
    )
    item = parse(text)
    assert item.base_type == "Divine Orb"
    assert item.name == "Divine Orb"
    assert item.properties.get("Stack Size") == "7/10"


def test_parse_corrupted_and_unidentified():
    text = (
        "Item Class: Body Armours\n"
        "Rarity: Rare\n"
        "Doom Shell\n"
        "Plate Vest\n"
        "--------\n"
        "Unidentified\n"
        "Corrupted\n"
    )
    item = parse(text)
    assert item.corrupted is True
    assert item.identified is False


def test_parse_empty_text():
    item = parse("")
    assert item.name is None and item.base_type is None


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
