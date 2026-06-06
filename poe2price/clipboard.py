"""Copy the hovered item out of the game — no external programs required.

Key injection uses **pynput**'s keyboard controller, which on X11 drives
``XTestFakeKeyEvent`` with a correct keysym→keycode lookup. This XTEST path
reaches the Wine/Proton game window reliably on X11 setups where other
synthetic-input methods fail to land in the focused game window.

``pynput`` is imported lazily inside the functions below: importing it opens an
X connection, so deferring the import keeps this module importable on headless
machines (e.g. CI) where the keystroke is never actually sent.

Clipboard read/write is intentionally NOT done here: ``QClipboard`` must be
used from the Qt GUI thread, so the orchestrator in :mod:`poe2price.__main__`
owns the clipboard and only calls :func:`send_copy_keystroke` from this module.
"""

from __future__ import annotations

# Stamped into the clipboard before copying so we can tell when the game has
# replaced it with the item text.
SENTINEL = "\x00poe2price-waiting\x00"

_keyboard = None  # pynput Controller, created on first use


def _controller():
    # Lazily created so importing this module never requires an X display
    # (keeps unit tests importable on headless machines).
    global _keyboard
    if _keyboard is None:
        from pynput.keyboard import Controller
        _keyboard = Controller()
    return _keyboard


def send_copy_keystroke() -> None:
    """Send Ctrl+C to the focused window (the game)."""
    from pynput.keyboard import Key

    _emit_copy(_controller(), Key.ctrl)


def _emit_copy(controller, ctrl_key) -> None:
    """Press and release Ctrl+C on *controller* using *ctrl_key* as modifier.

    Split out from :func:`send_copy_keystroke` so the key sequence can be unit
    tested without importing pynput (which needs an X display).
    """
    controller.press(ctrl_key)
    controller.press("c")
    controller.release("c")
    controller.release(ctrl_key)
