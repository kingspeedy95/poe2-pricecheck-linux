"""Tests for the copy-keystroke helper (no real key injection)."""

import poe2price.clipboard as clip
from poe2price.clipboard import SENTINEL, send_copy_keystroke


class _FakeController:
    def __init__(self):
        self.events = []

    def press(self, key):
        self.events.append(("press", str(key)))

    def release(self, key):
        self.events.append(("release", str(key)))


def test_sentinel_is_distinctive():
    # Must be something the game would never put on the clipboard.
    assert "poe2price" in SENTINEL
    assert SENTINEL.startswith("\x00")


def test_send_copy_keystroke_presses_ctrl_c(monkeypatch):
    fake = _FakeController()
    monkeypatch.setattr(clip, "_controller", lambda: fake)
    send_copy_keystroke()
    kinds = [kind for kind, _ in fake.events]
    # ctrl down, c down, c up, ctrl up — press before release for both.
    assert kinds == ["press", "press", "release", "release"]
    # 'c' is pressed while ctrl is still held.
    assert any("press" == k and "c" in v for k, v in fake.events)
