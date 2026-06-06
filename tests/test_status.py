"""Tests for the status toast and app icon (offscreen Qt)."""

import pytest


def test_app_icon_loads(qapp):
    from poe2price.status import app_icon

    icon = app_icon()
    assert not icon.isNull(), "bundled app icon should load"


@pytest.fixture
def toast(qapp):
    from poe2price.status import StatusToast

    t = StatusToast()
    yield t
    t.close()


def test_show_message_sets_text_and_shows(toast):
    toast.show_message("Waiting for Path of Exile 2 to start…")
    assert "Waiting" in toast._label.text()
    assert toast.isVisible()


def test_auto_hide_starts_timer(toast):
    toast.show_message("detected", auto_hide_ms=5000)
    assert toast._hide_timer.isActive()
    assert toast._hide_timer.remainingTime() > 0


def test_no_auto_hide_when_unset(toast):
    toast.show_message("persistent")
    assert not toast._hide_timer.isActive()


def test_has_logo_pixmap(toast):
    # The toast shows the app logo next to the text.
    assert toast._icon.pixmap() is not None
    assert not toast._icon.pixmap().isNull()
