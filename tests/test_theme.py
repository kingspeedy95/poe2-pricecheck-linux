"""Tests for the theme palette helpers."""

from poe2price import theme


def test_rarity_color_known():
    assert theme.rarity_color("Unique") == theme.RARITY_COLORS["Unique"]
    assert theme.rarity_color("Magic") == "#8888ff"


def test_rarity_color_falls_back():
    assert theme.rarity_color(None) == theme.TEXT
    assert theme.rarity_color("Nonsense") == theme.TEXT


def test_roll_quality_color_buckets():
    assert theme.roll_quality_color(1.0) == theme.GOOD
    assert theme.roll_quality_color(0.5) == theme.GOLD
    assert theme.roll_quality_color(0.0) == theme.DANGER


def test_roll_quality_color_clamps():
    # Out-of-range inputs must not raise and stay within the buckets.
    assert theme.roll_quality_color(5.0) == theme.GOOD
    assert theme.roll_quality_color(-3.0) == theme.DANGER


def test_window_stylesheet_mentions_palette():
    css = theme.window_stylesheet()
    assert theme.BG in css and theme.BORDER in css
