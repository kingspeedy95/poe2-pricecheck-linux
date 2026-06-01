"""Copy the hovered item out of the game and read it back.

This is the piece Exiled Exchange 2 gets wrong on this machine: its bundled
``uiohook-napi`` key injection does not reach the game, while ``xdotool``
(plain XTEST to the focused window) does.  So we drive ``xdotool`` directly.

Flow: stamp the clipboard with a sentinel, send Ctrl+C to the game, then
poll until the clipboard changes (the game replaced it with the item text).
"""

from __future__ import annotations

import subprocess
import time

_SENTINEL = "\x00poe2price-waiting\x00"


def _xclip_read() -> str:
    try:
        r = subprocess.run(
            ["xclip", "-selection", "clipboard", "-o"],
            capture_output=True, text=True, timeout=2,
        )
        return r.stdout
    except Exception:
        return ""


def _xclip_write(text: str) -> None:
    subprocess.run(
        ["xclip", "-selection", "clipboard"],
        input=text, text=True, timeout=2, check=False,
    )


def _send_ctrl_c() -> None:
    # Explicit down/tap/up of Ctrl+C via XTEST to the focused window. Proven
    # to work where uiohook's injection silently failed.
    subprocess.run(["xdotool", "keydown", "ctrl"], timeout=2, check=False)
    subprocess.run(["xdotool", "key", "c"], timeout=2, check=False)
    subprocess.run(["xdotool", "keyup", "ctrl"], timeout=2, check=False)


def copy_item(timeout: float = 0.6) -> str | None:
    """Copy the item under the cursor and return its text, or ``None``.

    ``None`` means nothing was copied within *timeout* seconds (no item under
    the cursor, or the game was not focused).
    """
    _xclip_write(_SENTINEL)
    _send_ctrl_c()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        text = _xclip_read()
        if text and text != _SENTINEL:
            return text
        time.sleep(0.02)
    return None
