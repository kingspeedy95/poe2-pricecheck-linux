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

from .clipboard import SENTINEL, send_copy_keystroke
from .config import CONFIG_PATH, Config
from .gamewatch import is_game_running
from .logsetup import get_logger, setup_logging
from .parser import Item, parse
from .singleton import acquire_single_instance_lock
from .status import StatusToast, app_icon
from .trade import TradeClient, TradeError
from .ui import PriceWindow

# How long to wait for the game to replace the clipboard after Ctrl+C.
_POLL_INTERVAL_MS = 30
_POLL_ATTEMPTS = 20  # ~600 ms total

# How often to check whether Path of Exile 2 is running.
_GAME_POLL_MS = 2000

log = get_logger()


class PriceWorker(QtCore.QObject):
    """Runs the trade lookup off the UI thread."""

    # Item, list[Listing], url, search summary
    finished = QtCore.pyqtSignal(object, object, str, str)
    failed = QtCore.pyqtSignal(str)

    def __init__(self, client: TradeClient, item: Item) -> None:
        super().__init__()
        self.client = client
        self.item = item

    def run(self) -> None:
        try:
            listings, url, summary = self.client.price_item(self.item)
        except TradeError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:  # network, JSON, ...
            self.failed.emit(f"Unexpected error: {exc}")
        else:
            self.finished.emit(self.item, listings, url, summary)


class App(QtCore.QObject):
    hotkey_pressed = QtCore.pyqtSignal()

    def __init__(self, cfg: Config) -> None:
        super().__init__()
        self.cfg = cfg
        self.client = TradeClient(cfg)
        self.window = PriceWindow()
        self.toast = StatusToast()
        self.clipboard = QtWidgets.QApplication.clipboard()

        self.hotkey_pressed.connect(self._on_hotkey)

        self._poll_timer = QtCore.QTimer()
        self._poll_timer.setInterval(_POLL_INTERVAL_MS)
        self._poll_timer.timeout.connect(self._poll_clipboard)
        self._poll_attempts = 0
        self._busy = False

        # System-tray icon so the user can see it's running and quit it.
        self.tray = self._build_tray()

        # Watch for the game launching/closing and reflect it in the toast/tray.
        self._game_running: bool | None = None
        self._game_timer = QtCore.QTimer()
        self._game_timer.setInterval(_GAME_POLL_MS)
        self._game_timer.timeout.connect(self._poll_game)
        self._game_timer.start()
        self._poll_game()  # set the initial state right away

    # -- system tray --------------------------------------------------------

    def _build_tray(self) -> QtWidgets.QSystemTrayIcon | None:
        if not QtWidgets.QSystemTrayIcon.isSystemTrayAvailable():
            return None
        tray = QtWidgets.QSystemTrayIcon(app_icon())
        tray.setToolTip("PoE2 Price Check")
        menu = QtWidgets.QMenu()
        header = menu.addAction("PoE2 Price Check")
        header.setEnabled(False)
        menu.addSeparator()
        quit_action = menu.addAction("Quit")
        quit_action.triggered.connect(QtWidgets.QApplication.quit)
        tray.setContextMenu(menu)
        tray.show()
        return tray

    # -- game watch ---------------------------------------------------------

    def _poll_game(self) -> None:
        running = is_game_running()
        if running == self._game_running:
            return  # no change
        self._game_running = running
        if running:
            self.toast.show_message(
                "Path of Exile 2 detected — price checker running in background.",
                auto_hide_ms=7000,
            )
            if self.tray:
                self.tray.setToolTip("PoE2 Price Check — game running")
        else:
            self.toast.show_message("Waiting for Path of Exile 2 to start…")
            if self.tray:
                self.tray.setToolTip("PoE2 Price Check — waiting for game")

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
            log.warning("Unrecognised clipboard text (%d chars)", len(text))
            self.window.show_error("Could not recognise an item in the clipboard.")
            return
        log.info("Pricing %s [%s]", item.display_name, item.rarity or "?")
        self.window.show_loading(item)
        self._start_lookup(item)

    # -- price lookup (worker thread) --------------------------------------

    def _start_lookup(self, item: Item) -> None:
        worker = PriceWorker(self.client, item)
        worker.finished.connect(self._on_finished)
        worker.failed.connect(self._on_failed)
        self._worker = worker  # keep a reference while it runs
        threading.Thread(target=worker.run, daemon=True).start()

    def _on_finished(self, item: Item, listings, url: str, summary: str) -> None:
        self._busy = False
        log.info("Result for %s: %d listings (%s)",
                 item.display_name, len(listings), summary)
        self.window.show_result(item, listings, url, summary)

    def _on_failed(self, message: str) -> None:
        self._busy = False
        log.warning("Lookup failed: %s", message)
        self.window.show_error(message)


def main() -> int:
    # Handle --version before touching Qt/pynput so it works headlessly (used to
    # smoke-test the packaged AppImage in CI).
    if "--version" in sys.argv[1:]:
        from poe2price import __version__
        print(f"poe2-pricecheck {__version__}")
        return 0

    setup_logging()
    cfg = Config.load()
    log.info("Starting poe2-pricecheck (league=%r, hotkey=%r)",
             cfg.league, cfg.hotkey)

    qt = QtWidgets.QApplication(sys.argv)
    qt.setQuitOnLastWindowClosed(False)  # live in the background
    qt.setWindowIcon(app_icon())

    # Only one instance may run — a second would fight over the global hotkey.
    lock = acquire_single_instance_lock()
    if lock is None:
        print("PoE2 Price Check is already running in the background.")
        QtWidgets.QMessageBox.information(
            None,
            "PoE2 Price Check",
            "PoE2 Price Check is already running in the background.",
        )
        return 0

    app = App(cfg)
    app._instance_lock = lock  # keep the lock handle alive for the whole run

    def on_activate() -> None:
        app.hotkey_pressed.emit()

    # Imported here (not at module top) so --version and headless imports don't
    # require an X display, which pynput needs at import time.
    from pynput import keyboard

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
