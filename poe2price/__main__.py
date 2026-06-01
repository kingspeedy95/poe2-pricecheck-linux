"""Entry point: wire the global hotkey to copy -> parse -> price -> popup.

Threading model:

* The hotkey is detected by pynput on its own thread; it emits a Qt signal.
* Clipboard access (``QClipboard``) must happen on the Qt GUI thread, so the
  copy + poll runs there, driven by a non-blocking ``QTimer`` (never sleeps
  the UI).
* Only the network call runs on a worker thread, reporting back via signals.

No external programs are used: key injection is pynput, clipboard is Qt.
"""

from __future__ import annotations

import sys
import threading

from PyQt6 import QtCore, QtWidgets

from pynput import keyboard

from .clipboard import SENTINEL, send_copy_keystroke
from .config import CONFIG_PATH, Config
from .parser import Item, parse
from .trade import TradeClient, TradeError
from .ui import PriceWindow

# How long to wait for the game to replace the clipboard after Ctrl+C.
_POLL_INTERVAL_MS = 30
_POLL_ATTEMPTS = 20  # ~600 ms total


class PriceWorker(QtCore.QObject):
    """Runs the trade lookup off the UI thread."""

    finished = QtCore.pyqtSignal(object, object, str)  # Item, list[Listing], url
    failed = QtCore.pyqtSignal(str)

    def __init__(self, client: TradeClient, item: Item) -> None:
        super().__init__()
        self.client = client
        self.item = item

    def run(self) -> None:
        try:
            listings, url = self.client.price_item(self.item)
        except TradeError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:  # network, JSON, ...
            self.failed.emit(f"Unexpected error: {exc}")
        else:
            self.finished.emit(self.item, listings, url)


class App(QtCore.QObject):
    hotkey_pressed = QtCore.pyqtSignal()

    def __init__(self, cfg: Config) -> None:
        super().__init__()
        self.cfg = cfg
        self.client = TradeClient(cfg)
        self.window = PriceWindow()
        self.clipboard = QtWidgets.QApplication.clipboard()

        self.hotkey_pressed.connect(self._on_hotkey)

        self._poll_timer = QtCore.QTimer()
        self._poll_timer.setInterval(_POLL_INTERVAL_MS)
        self._poll_timer.timeout.connect(self._poll_clipboard)
        self._poll_attempts = 0
        self._busy = False

    # -- copy (Qt thread) ---------------------------------------------------

    def _on_hotkey(self) -> None:
        if self._busy:
            return
        self._busy = True
        self.clipboard.setText(SENTINEL)
        try:
            send_copy_keystroke()
        except Exception as exc:
            self._busy = False
            self.window.show_error(f"Could not send copy keystroke: {exc}")
            return
        self._poll_attempts = 0
        self._poll_timer.start()

    def _poll_clipboard(self) -> None:
        self._poll_attempts += 1
        text = self.clipboard.text()
        if text and text != SENTINEL:
            self._poll_timer.stop()
            self._handle_item_text(text)
        elif self._poll_attempts >= _POLL_ATTEMPTS:
            self._poll_timer.stop()
            self._busy = False
            self.window.show_error(
                "Nothing copied. Hover an item in-game and keep the game focused."
            )

    def _handle_item_text(self, text: str) -> None:
        item = parse(text)
        if not (item.name or item.base_type):
            self._busy = False
            self.window.show_error("Could not recognise an item in the clipboard.")
            return
        self.window.show_loading(item)
        self._start_lookup(item)

    # -- price lookup (worker thread) --------------------------------------

    def _start_lookup(self, item: Item) -> None:
        worker = PriceWorker(self.client, item)
        worker.finished.connect(self._on_finished)
        worker.failed.connect(self._on_failed)
        self._worker = worker  # keep a reference while it runs
        threading.Thread(target=worker.run, daemon=True).start()

    def _on_finished(self, item: Item, listings, url: str) -> None:
        self._busy = False
        self.window.show_result(item, listings, url)

    def _on_failed(self, message: str) -> None:
        self._busy = False
        self.window.show_error(message)


def main() -> int:
    cfg = Config.load()

    qt = QtWidgets.QApplication(sys.argv)
    qt.setQuitOnLastWindowClosed(False)  # live in the background

    app = App(cfg)

    def on_activate() -> None:
        app.hotkey_pressed.emit()

    hotkey = keyboard.GlobalHotKeys({cfg.hotkey: on_activate})
    hotkey.daemon = True
    hotkey.start()

    print(
        f"poe2-pricecheck-linux running. League: {cfg.league!r}. "
        f"Hotkey: {cfg.hotkey}. Hover an item and press it. Ctrl+C here to quit."
    )

    # Startup session check / warning.
    ok, message = app.client.check_session()
    if ok:
        print(f"POESESSID OK: {message}.")
    else:
        print(
            f"WARNING: {message}. Trade requests may be blocked by Cloudflare. "
            f"Add a valid POESESSID to {CONFIG_PATH}."
        )

    return qt.exec()


if __name__ == "__main__":
    raise SystemExit(main())
