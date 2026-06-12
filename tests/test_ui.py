"""Tests for the price popup window (offscreen Qt)."""

import pytest

from poe2price.parser import Item
from poe2price.stats import StatFilter
from poe2price.trade import Listing, SearchSpec


def _rare_spec():
    return SearchSpec(
        type="Sapphire Ring", ilvl_min=82, ilvl_enabled=False,
        stats=[
            StatFilter(id="explicit.stat_life", label="+# to maximum Life", min=80),
            StatFilter(id="explicit.stat_cold", label="+#% Cold Resistance", min=30),
        ],
        summary="Sapphire Ring + 2 stat filters",
    )


_RING = Item(rarity="Rare", name="Doom Coil", base_type="Sapphire Ring", item_level=82)


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


# --- interactive filter panel -----------------------------------------------

def test_spec_builds_one_row_per_mod(window):
    window.show_result(_RING, [], "http://x", "s", _rare_spec())
    assert len(window._rows) == 2
    assert window._filter_box.isVisibleTo(window)
    assert window._rows[0].check.text() == "+# to maximum Life"


def test_no_spec_hides_filter_panel(window):
    # Currency / unique-by-name: spec is None, panel stays hidden.
    window.show_result(Item(rarity="Currency", name="Divine Orb"),
                       [Listing(1, "divine", "a", "@a")], "http://x", "exchange", None)
    assert not window._filter_box.isVisibleTo(window)


def test_search_button_emits_spec_synced_from_ui(window):
    spec = _rare_spec()
    window.show_result(_RING, [], "http://x", "s", spec)
    captured = []
    window.search_requested.connect(captured.append)

    window._rows[0].check.setChecked(False)     # drop the life filter
    window._rows[1].min_edit.setText("45")       # tighten cold res min
    window._do_search()

    assert captured == [spec]
    assert spec.stats[0].enabled is False
    assert spec.stats[1].min == 45.0
    assert spec.active_stat_count == 1


def test_ilvl_and_rarity_toggles_sync(window):
    spec = SearchSpec(type="Utility Belt", rarity="normal", rarity_enabled=True,
                      ilvl_min=82, ilvl_enabled=True,
                      summary="white base: Utility Belt, ilvl 82+")
    window.show_result(Item(rarity="Normal", base_type="Utility Belt", item_level=82),
                       [], "http://x", "s", spec)
    assert window._rows == []  # white base has no editable mods
    window._ilvl_check.setChecked(False)         # widen to all item levels
    window._ilvl_edit.setText("84")
    window._do_search()
    assert spec.ilvl_enabled is False
    assert spec.ilvl_min == 84


def test_update_listings_refreshes_body_and_url(window):
    window.show_result(_RING, [], "http://x", "s", _rare_spec())
    window.update_listings([Listing(5, "exalted", "acc", "@acc")], "http://y")
    assert "5" in window._body.text()
    assert window._url == "http://y"


def test_clamp_keeps_window_on_screen(window):
    from PyQt6 import QtCore

    window.show_error("boom")
    far = QtCore.QPoint(10**6, 10**6)
    clamped = window._clamp_to_screen(far)
    screen_geo = window.screen().availableGeometry()
    assert clamped.x() + window.width() <= screen_geo.right() + 1
    assert clamped.y() + window.height() <= screen_geo.bottom() + 1
