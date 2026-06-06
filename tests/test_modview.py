"""Tests for the mods HTML rendering."""

from poe2price.modview import mod_display, mod_tag, mods_html, quality_bar_html
from poe2price.parser import Item, Modifier


def test_mod_tag_prefix_suffix_with_tier():
    assert "P1" in mod_tag(Modifier(text="x", affix="prefix", tier=1, kind="explicit"))
    assert "S3" in mod_tag(Modifier(text="x", affix="suffix", tier=3, kind="explicit"))


def test_mod_tag_implicit():
    assert "impl" in mod_tag(Modifier(text="x", kind="implicit"))


def test_mod_tag_empty_when_unknown():
    assert mod_tag(Modifier(text="x", kind="explicit")) == ""


def test_mod_display_uses_raw_when_present():
    mod = Modifier(text="+# to maximum Life", values=[95], raw="+95 to maximum Life")
    assert mod_display(mod) == "+95 to maximum Life"


def test_mod_display_folds_values_when_no_raw():
    mod = Modifier(text="+# to maximum Life", values=[95])
    assert mod_display(mod) == "+95 to maximum Life"


def test_mod_display_folds_multiple_values():
    mod = Modifier(text="Adds # to # Physical Damage", values=[5, 12])
    assert mod_display(mod) == "Adds 5 to 12 Physical Damage"


def test_quality_bar_shows_percentage_and_color():
    html = quality_bar_html(0.5)
    assert "50%" in html
    # 5 segments, half filled -> some filled and some empty glyphs.
    assert "▰" in html and "▱" in html


def test_mods_html_empty_for_no_mods():
    assert mods_html(Item(rarity="Currency", base_type="Divine Orb")) == ""


def test_mods_html_includes_text_tier_and_quality():
    item = Item(rarity="Rare", base_type="Ring", explicits=[
        Modifier(text="+# to maximum Life", values=[95], ranges=[(80, 99)],
                 tier=1, raw="+95 to maximum Life"),
    ])
    html = mods_html(item)
    assert "+95 to maximum Life" in html
    assert "T1" in html
    assert "%" in html  # roll-quality rendered
    assert "<table" in html
