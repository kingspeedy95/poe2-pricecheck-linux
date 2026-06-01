"""Entry point: wire the global hotkey to copy -> parse -> price -> popup.

The hotkey is detected on a background thread (pynput).  All the Qt work
must happen on the main thread, and the network call must *not* block the UI,
so the flow is:

    pynput thread  --signal-->  Qt main thread  --worker thread-->  network
                                      ^                                 |
                                      +-------------- signal -----------+
"""

from __future__ import annotations

import sys
import threading

from PyQt6 import QtCore, QtWidgets
from pynput import keyboard

from .clipboard import copy_item
from .config import Config
from .parser import Item, parse
from .trade import TradeClient, TradeError
from .ui import PriceWindow


class Worker(QtCore.QObject):
    """Runs a price check off the UI thread and reports back via signals."""

    loading = QtCore.pyqtSignal(object)            # Item
    finished = QtCore.pyqtSignal(object, object, str)  # Item, list[Listing], url
    failed = QtCore.pyqtSignal(str)

    def __init__(self, cfg: Config) -> None:
        super().__init__()
        self.client = TradeClient(cfg)

    def run(self) -> None:
        text = copy_item()
        if not text:
            self.failed.emit(
                "Nothing copied. Hover an item in-game and keep the game focused."
            )
            return
        item: Item = parse(text)
        if not (item.name or item.base_type):
            self.failed.emit("Could not recognise an item in the clipboard.")
            return
        self.loading.emit(item)
        try:
            listings, url = self.client.price_item(item)
        except TradeError as exc:
            self.failed.emit(str(exc))
            return
        except Exception as exc:  # network, JSON, ...
            self.failed.emit(f"Unexpected error: {exc}")
            return
        self.finished.emit(item, listings, url)


class App(QtCore.QObject):
    hotkey_pressed = QtCore.pyqtSignal()

    def __init__(self, cfg: Config) -> None:
        super().__init__()
        self.cfg = cfg
        self.window = PriceWindow()
        self.hotkey_pressed.connect(self._on_hotkey)

    def _on_hotkey(self) -> None:
        worker = Worker(self.cfg)
        worker.loading.connect(self.window.show_loading)
        worker.finished.connect(self.window.show_result)
        worker.failed.connect(self.window.show_error)
        # Keep a reference so it isn't garbage-collected mid-run.
        self._worker = worker
        threading.Thread(target=worker.run, daemon=True).start()


def main() -> int:
    cfg = Config.load()

    qt = QtWidgets.QApplication(sys.argv)
    qt.setQuitOnLastWindowClosed(False)  # live in the tray/background

    app = App(cfg)

    # pynput runs the hotkey listener on its own thread; bounce into Qt.
    def on_activate() -> None:
        app.hotkey_pressed.emit()

    hotkey = keyboard.GlobalHotKeys({cfg.hotkey: on_activate})
    hotkey.daemon = True
    hotkey.start()

    print(f"poe2-pricecheck-linux running. League: {cfg.league!r}. "
          f"Hotkey: {cfg.hotkey}. Hover an item and press it. Ctrl+C here to quit.")
    if not cfg.poesessid:
        print("WARNING: no POESESSID set in config — trade requests may be "
              "blocked by Cloudflare. See README.")

    return qt.exec()


if __name__ == "__main__":
    raise SystemExit(main())
