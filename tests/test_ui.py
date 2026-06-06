"""Tests for the price popup window (offscreen Qt)."""

import pytest

from poe2price.parser import Item
from poe2price.trade import Listing


@pytest.fixture
def window(qapp):
    from poe2price.ui import PriceWindow

    w = PriceWindow()
    yield w
    w.close()


def test_show_result_lists_prices(window):
    item = Item(rarity="Unique", name="Astramentis", base_type="Stellar Amulet")
    window.show_result(item, [Listing(1, "exalted", "acc#1", "@a")], "http://x")
    assert "Astramentis" in window._title.text()
    assert "1" in window._body.text()
    assert window._url == "http://x"


def test_show_result_more_indicator(window):
    listings = [Listing(i, "exalted", f"s{i}", f"@s{i}") for i in range(12)]
    window.show_result(Item(rarity="Unique", name="X"), listings, "http://x", "")
    assert "+3 more" in window._body.text()  # 12 - 9 shown


def test_show_result_no_more_indicator_when_few(window):
    listings = [Listing(i, "exalted", f"s{i}", f"@s{i}") for i in range(4)]
    window.show_result(Item(rarity="Unique", name="X"), listings, "http://x", "")
    assert "more" not in window._body.text()


def test_show_result_empty(window):
    window.show_result(Item(rarity="Unique", name="X"), [], "http://x")
    assert "no online listings" in window._body.text()


def test_show_error(window):
    window.show_error("boom")
    assert "boom" in window._body.text()
    assert "failed" in window._title.text().lower()


def test_hide_remembers_position(window):
    window.show_error("boom")
    from PyQt6 import QtCore

    window.move(QtCore.QPoint(123, 234))
    window.hide()
    assert window._last_pos == QtCore.QPoint(123, 234)
    # Next present reuses the remembered spot.
    window.show_error("again")
    assert window.pos() == QtCore.QPoint(123, 234)


def test_copy_whisper_puts_text_on_clipboard(window, qapp):
    item = Item(rarity="Unique", name="X")
    listings = [
        Listing(1, "exalted", "a", "@seller_a hi"),
        Listing(2, "exalted", "b", "@seller_b hi"),
    ]
    window.show_result(item, listings, "http://x", "by name")
    assert window._copy_whisper(1) is True
    assert qapp.clipboard().text() == "@seller_b hi"


def test_copy_whisper_out_of_range(window):
    window.show_result(Item(rarity="Unique", name="X"), [], "http://x", "")
    assert window._copy_whisper(0) is False  # no listings


def test_copy_whisper_missing_whisper(window, qapp):
    listings = [Listing(1, "exalted", "a", None)]
    window.show_result(Item(rarity="Unique", name="X"), listings, "http://x", "")
    assert window._copy_whisper(0) is False


def test_clamp_keeps_window_on_screen(window):
    from PyQt6 import QtCore

    window.show_error("boom")
    far = QtCore.QPoint(10**6, 10**6)
    clamped = window._clamp_to_screen(far)
    screen_geo = window.screen().availableGeometry()
    assert clamped.x() + window.width() <= screen_geo.right() + 1
    assert clamped.y() + window.height() <= screen_geo.bottom() + 1
