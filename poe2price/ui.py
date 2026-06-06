"""A small frameless popup that shows the price result near the cursor.

The window is draggable (click anywhere and drag), remembers where it was when
last closed, has an ✕ button in the corner, and is clamped to stay fully on a
single monitor so it never drifts off the edge onto another screen.
"""

from __future__ import annotations

from PyQt6 import QtCore, QtGui, QtWidgets

from .links import poe2db_url, wiki_url
from .parser import Item
from .trade import Listing, summarize


class PriceWindow(QtWidgets.QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowFlags(
            QtCore.Qt.WindowType.FramelessWindowHint
            | QtCore.Qt.WindowType.WindowStaysOnTopHint
            | QtCore.Qt.WindowType.Tool
        )
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_ShowWithoutActivating)

        # Where the window was when last closed; reused on the next show so the
        # popup keeps coming back to the same spot. None until first close.
        self._last_pos: QtCore.QPoint | None = None
        # Offset between the cursor and the window's top-left while dragging.
        self._drag_offset: QtCore.QPoint | None = None
        # The item currently shown, for the wiki/poe2db quick-link keys.
        self._item: Item | None = None
        self._url: str | None = None
        self._listings: list[Listing] = []  # for 1-9 copy-whisper

        self._layout = QtWidgets.QVBoxLayout(self)
        self._layout.setContentsMargins(12, 8, 10, 10)
        self._layout.setSpacing(4)

        # -- header row: title (left) + close button (right) ----------------
        self._title = QtWidgets.QLabel()
        self._title.setStyleSheet("font-weight: bold; font-size: 14px;")
        self._close_btn = QtWidgets.QPushButton("✕")
        self._close_btn.setFixedSize(18, 18)
        self._close_btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self._close_btn.setToolTip("Close")
        self._close_btn.setStyleSheet(
            "QPushButton { color: #999; border: none; background: transparent; "
            "font-size: 13px; font-weight: bold; }"
            "QPushButton:hover { color: #fff; background: #803333; "
            "border-radius: 4px; }"
        )
        self._close_btn.clicked.connect(self.hide)

        header = QtWidgets.QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(8)
        header.addWidget(self._title, 1)
        header.addWidget(
            self._close_btn, 0, QtCore.Qt.AlignmentFlag.AlignTop
        )
        self._layout.addLayout(header)

        self._subtitle = QtWidgets.QLabel()
        self._subtitle.setStyleSheet("color: #aaa; font-size: 11px;")
        self._body = QtWidgets.QLabel()
        self._body.setTextFormat(QtCore.Qt.TextFormat.RichText)
        self._hint = QtWidgets.QLabel()
        self._hint.setStyleSheet("color: #666; font-size: 10px;")

        for w in (self._subtitle, self._body, self._hint):
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
        self._hint.setText("Drag to move  ·  Esc / ✕ to close")
        self._present()

    def show_result(
        self, item: Item, listings: list[Listing], url: str, summary: str = ""
    ) -> None:
        self._title.setText(item.display_name)
        rarity = item.rarity or ""
        self._subtitle.setText(f"{rarity} · {summary}" if summary else rarity)
        if listings:
            stats = summarize(listings)
            header = (
                f"<div style='font-size:14px; color:#e8c87a; margin-bottom:3px'>"
                f"{stats.text}</div>"
            )
            rows = "<br>".join(
                f"<span style='color:#666'>{n}.</span> <b>{li.price_text}</b>"
                + (f" &middot; <span style='color:#888'>{li.account}</span>" if li.account else "")
                for n, li in enumerate(listings[:9], start=1)
            )
            self._body.setText(header + rows)
        else:
            self._body.setText("<span style='color:#c66'>no online listings found</span>")
        self._hint.setText("Enter trade · 1-9 copy whisper · W wiki · B poe2db · Esc/✕")
        self._url = url
        self._item = item
        self._listings = listings
        self._present()

    def show_error(self, message: str) -> None:
        self._title.setText("Price check failed")
        self._subtitle.setText("")
        self._body.setText(f"<span style='color:#c66'>{message}</span>")
        self._hint.setText("Drag to move  ·  Esc / ✕ to close")
        self._present()

    # -- placement ----------------------------------------------------------

    def _present(self) -> None:
        self.adjustSize()
        if self._last_pos is not None:
            target = self._last_pos
        else:
            cursor = QtGui.QCursor.pos()
            target = QtCore.QPoint(cursor.x() + 16, cursor.y() + 16)
        self.move(self._clamp_to_screen(target))
        self.show()
        self.raise_()

    def _clamp_to_screen(self, point: QtCore.QPoint) -> QtCore.QPoint:
        """Keep the whole window inside the monitor under *point*."""
        screen = (
            QtWidgets.QApplication.screenAt(point)
            or QtWidgets.QApplication.primaryScreen()
        )
        area = screen.availableGeometry()
        w, h = self.width(), self.height()
        x = min(max(point.x(), area.left()), max(area.left(), area.right() - w + 1))
        y = min(max(point.y(), area.top()), max(area.top(), area.bottom() - h + 1))
        return QtCore.QPoint(x, y)

    # -- dragging -----------------------------------------------------------

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self._drag_offset = (
                event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            )
            event.accept()

    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:
        if (
            self._drag_offset is not None
            and event.buttons() & QtCore.Qt.MouseButton.LeftButton
        ):
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:
        self._drag_offset = None

    # -- close / remember position ------------------------------------------

    def hideEvent(self, event: QtGui.QHideEvent) -> None:
        # Remember wherever the window ended up so it reappears in place.
        self._last_pos = self.pos()
        super().hideEvent(event)

    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        key = event.key()
        if key == QtCore.Qt.Key.Key_Escape:
            self.hide()
        elif key in (QtCore.Qt.Key.Key_Return, QtCore.Qt.Key.Key_Enter):
            self._open(self._url)
            self.hide()
        elif key == QtCore.Qt.Key.Key_W and self._item is not None:
            self._open(wiki_url(self._item))
        elif key == QtCore.Qt.Key.Key_B and self._item is not None:
            self._open(poe2db_url(self._item))
        elif QtCore.Qt.Key.Key_1 <= key <= QtCore.Qt.Key.Key_9:
            self._copy_whisper(key - QtCore.Qt.Key.Key_1)

    def _copy_whisper(self, index: int) -> bool:
        """Copy the whisper for listing *index* (0-based) to the clipboard."""
        if not (0 <= index < len(self._listings)):
            return False
        whisper = self._listings[index].whisper
        if not whisper:
            return False
        QtWidgets.QApplication.clipboard().setText(whisper)
        self._hint.setText(f"✓ copied whisper #{index + 1} — paste in-game chat")
        return True

    @staticmethod
    def _open(url: str | None) -> None:
        if url:
            QtGui.QDesktopServices.openUrl(QtCore.QUrl(url))
