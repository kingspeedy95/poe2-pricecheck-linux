"""A small frameless popup that shows the price result near the cursor."""

from __future__ import annotations

from PyQt6 import QtCore, QtGui, QtWidgets

from .parser import Item
from .trade import Listing


class PriceWindow(QtWidgets.QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowFlags(
            QtCore.Qt.WindowType.FramelessWindowHint
            | QtCore.Qt.WindowType.WindowStaysOnTopHint
            | QtCore.Qt.WindowType.Tool
        )
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_ShowWithoutActivating)

        self._layout = QtWidgets.QVBoxLayout(self)
        self._layout.setContentsMargins(12, 10, 12, 10)
        self._layout.setSpacing(4)

        self._title = QtWidgets.QLabel()
        self._title.setStyleSheet("font-weight: bold; font-size: 14px;")
        self._subtitle = QtWidgets.QLabel()
        self._subtitle.setStyleSheet("color: #aaa; font-size: 11px;")
        self._body = QtWidgets.QLabel()
        self._body.setTextFormat(QtCore.Qt.TextFormat.RichText)
        self._hint = QtWidgets.QLabel("Esc to close")
        self._hint.setStyleSheet("color: #666; font-size: 10px;")

        for w in (self._title, self._subtitle, self._body, self._hint):
            self._layout.addWidget(w)

        self.setStyleSheet(
            "PriceWindow { background: #1b1b1f; border: 1px solid #444; "
            "border-radius: 8px; } QLabel { color: #ddd; }"
        )

    # -- display ------------------------------------------------------------

    def show_loading(self, item: Item) -> None:
        self._title.setText(item.display_name)
        self._subtitle.setText(item.rarity or "")
        self._body.setText("<i>searching the trade API…</i>")
        self._hint.setText("Esc to close")
        self._present()

    def show_result(self, item: Item, listings: list[Listing], url: str) -> None:
        self._title.setText(item.display_name)
        self._subtitle.setText(item.rarity or "")
        if listings:
            rows = "<br>".join(
                f"&bull; <b>{l.price_text}</b>"
                + (f" &middot; <span style='color:#888'>{l.account}</span>" if l.account else "")
                for l in listings[:8]
            )
            self._body.setText(rows)
        else:
            self._body.setText("<span style='color:#c66'>no online listings found</span>")
        self._hint.setText("Enter to open in browser  ·  Esc to close")
        self._url = url
        self._present()

    def show_error(self, message: str) -> None:
        self._title.setText("Price check failed")
        self._subtitle.setText("")
        self._body.setText(f"<span style='color:#c66'>{message}</span>")
        self._hint.setText("Esc to close")
        self._present()

    # -- helpers ------------------------------------------------------------

    def _present(self) -> None:
        self.adjustSize()
        pos = QtGui.QCursor.pos()
        self.move(pos.x() + 16, pos.y() + 16)
        self.show()
        self.raise_()

    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        key = event.key()
        if key == QtCore.Qt.Key.Key_Escape:
            self.hide()
        elif key in (QtCore.Qt.Key.Key_Return, QtCore.Qt.Key.Key_Enter):
            url = getattr(self, "_url", None)
            if url:
                QtGui.QDesktopServices.openUrl(QtCore.QUrl(url))
            self.hide()
