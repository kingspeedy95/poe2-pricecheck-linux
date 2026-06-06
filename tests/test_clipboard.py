"""Tests for the copy-keystroke helper (no real key injection)."""

from poe2price.clipboard import SENTINEL, _emit_copy


class _FakeController:
    def __init__(self):
        self.events = []

    def press(self, key):
        self.events.append(("press", key))

    def release(self, key):
        self.events.append(("release", key))


def test_sentinel_is_distinctive():
    # Must be something the game would never put on the clipboard.
    assert "poe2price" in SENTINEL
    assert SENTINEL.startswith("\x00")


def test_emit_copy_presses_ctrl_c_in_order():
    # Uses a sentinel ctrl key so the test never imports pynput (no X needed).
    fake = _FakeController()
    _emit_copy(fake, "CTRL")
    assert fake.events == [
        ("press", "CTRL"),
        ("press", "c"),
        ("release", "c"),
        ("release", "CTRL"),
    ]
