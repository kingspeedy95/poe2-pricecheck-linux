"""Copy the hovered item out of the game — no external programs required.

Key injection uses **pynput**'s keyboard controller, which on X11 drives
``XTestFakeKeyEvent`` with a correct keysym→keycode lookup. That is the same
XTEST path ``xdotool`` uses (proven to work on this machine) and avoids the
faulty internal keycode table that makes Exiled Exchange 2's ``uiohook``
injection fail here.

Clipboard read/write is intentionally NOT done here: ``QClipboard`` must be
used from the Qt GUI thread, so the orchestrator in :mod:`poe2price.__main__`
owns the clipboard and only calls :func:`send_copy_keystroke` from this module.
"""

from __future__ import annotations

from pynput.keyboard import Controller, Key

# Stamped into the clipboard before copying so we can tell when the game has
# replaced it with the item text.
SENTINEL = "\x00poe2price-waiting\x00"

_keyboard: Controller | None = None


def _controller() -> Controller:
    # Lazily created so importing this module never requires an X display
    # (keeps unit tests importable on headless machines).
    global _keyboard
    if _keyboard is None:
        _keyboard = Controller()
    return _keyboard


def send_copy_keystroke() -> None:
    """Send Ctrl+C to the focused window (the game)."""
    kb = _controller()
    kb.press(Key.ctrl)
    kb.press("c")
    kb.release("c")
    kb.release(Key.ctrl)
