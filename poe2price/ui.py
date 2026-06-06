"""A small frameless popup that shows the price result near the cursor.

The window is draggable (click anywhere and drag), remembers where it was when
last closed, has an ✕ button in the corner, and is clamped to stay fully on a
single monitor so it never drifts off the edge onto another screen.
"""

from __future__ import annotations

from PyQt6 import QtCore, QtGui, QtWidgets

from . import theme
from .links import poe2db_url, wiki_url
from .modview import mods_html
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

        self.setMinimumWidth(300)
        self.setMaximumWidth(460)
        self._layout = QtWidgets.QVBoxLayout(self)
        self._layout.setContentsMargins(14, 11, 12, 11)
        self._layout.setSpacing(7)

        # -- header: name (rarity-coloured) + close button ------------------
        self._title = QtWidgets.QLabel()  # item name
        self._title.setStyleSheet("font-weight: bold; font-size: 15px;")
        self._close_btn = QtWidgets.QPushButton("✕")
        self._close_btn.setFixedSize(18, 18)
        self._close_btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self._close_btn.setToolTip("Close")
        self._close_btn.setStyleSheet(
            f"QPushButton {{ color: {theme.TEXT_DIM}; border: none; "
            f"background: transparent; font-size: 13px; font-weight: bold; }}"
            f"QPushButton:hover {{ color: #fff; background: #803333; "
            f"border-radius: 4px; }}"
        )
        self._close_btn.clicked.connect(self.hide)

        header = QtWidgets.QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(8)
        header.addWidget(self._title, 1)
        header.addWidget(self._close_btn, 0, QtCore.Qt.AlignmentFlag.AlignTop)
        self._layout.addLayout(header)

        # base type · item level
        self._subtitle = QtWidgets.QLabel()
        self._subtitle.setWordWrap(True)
        self._subtitle.setStyleSheet(
            f"color: {theme.TEXT_DIM}; font-size: 11px;"
        )
        self._layout.addWidget(self._subtitle)

        # -- price band (raised panel) --------------------------------------
        self._price = QtWidgets.QLabel()
        self._price.setStyleSheet(
            f"color: {theme.GOLD}; font-size: 18px; font-weight: bold;"
        )
        self._price_sub = QtWidgets.QLabel()
        self._price_sub.setWordWrap(True)
        self._price_sub.setStyleSheet(
            f"color: {theme.TEXT_DIM}; font-size: 10px;"
        )
        band_inner = QtWidgets.QVBoxLayout()
        band_inner.setContentsMargins(10, 7, 10, 7)
        band_inner.setSpacing(1)
        band_inner.addWidget(self._price)
        band_inner.addWidget(self._price_sub)
        self._band = QtWidgets.QFrame()
        self._band.setObjectName("band")
        self._band.setStyleSheet(
            f"#band {{ background: {theme.BG_PANEL}; border: 1px solid "
            f"{theme.BORDER}; border-radius: 7px; }}"
        )
        self._band.setLayout(band_inner)
        self._layout.addWidget(self._band)

        # -- mods -----------------------------------------------------------
        self._mods = QtWidgets.QLabel()
        self._mods.setTextFormat(QtCore.Qt.TextFormat.RichText)
        self._mods.setWordWrap(True)
        self._mods.setStyleSheet("font-size: 11px;")
        self._layout.addWidget(self._mods)

        # -- divider before listings ----------------------------------------
        self._sep = QtWidgets.QFrame()
        self._sep.setFixedHeight(1)
        self._sep.setStyleSheet(f"background: {theme.BORDER}; border: none;")
        self._layout.addWidget(self._sep)

        # -- listings -------------------------------------------------------
        self._body = QtWidgets.QLabel()
        self._body.setTextFormat(QtCore.Qt.TextFormat.RichText)
        self._body.setWordWrap(True)
        self._body.setStyleSheet("font-size: 12px;")
        self._layout.addWidget(self._body)

        # -- footer hint ----------------------------------------------------
        self._hint = QtWidgets.QLabel()
        self._hint.setStyleSheet(f"color: {theme.TEXT_FAINT}; font-size: 10px;")
        self._layout.addWidget(self._hint)

        self.setStyleSheet(theme.window_stylesheet())

    # -- display ------------------------------------------------------------

    def show_loading(self, item: Item) -> None:
        self._set_header(item)
        self._band.hide()
        self._mods.hide()
        self._sep.hide()
        self._body.setText(
            f"<i style='color:{theme.TEXT_DIM}'>searching the trade API…</i>"
        )
        self._hint.setText("Drag to move  ·  Esc / ✕ to close")
        self._present()

    def show_result(
        self, item: Item, listings: list[Listing], url: str, summary: str = ""
    ) -> None:
        self._set_header(item)

        stats = summarize(listings)
        self._price.setText(stats.headline)
        detail = stats.detail
        if summary:
            detail = f"{detail}  ·  {summary}" if detail else summary
        self._price_sub.setText(detail)
        self._band.show()

        mods = mods_html(item)
        self._mods.setText(mods)
        self._mods.setVisible(bool(mods))
        self._sep.show()

        if listings:
            rows = "".join(
                f"<div style='margin:2px 0'>"
                f"<span style='color:{theme.TEXT_FAINT}'>{n}.</span> "
                f"<span style='color:{theme.GOLD_DIM}; font-weight:bold'>{li.price_text}</span>"
                + (f" <span style='color:{theme.TEXT_DIM}'>&middot; "
                   f"{li.account}</span>" if li.account else "")
                + "</div>"
                for n, li in enumerate(listings[:9], start=1)
            )
            extra = len(listings) - 9
            if extra > 0:
                rows += (
                    f"<div style='margin-top:3px; color:{theme.TEXT_FAINT}'>"
                    f"+{extra} more — press Enter for the full list</div>"
                )
            self._body.setText(rows)
        else:
            self._body.setText(
                f"<span style='color:{theme.DANGER}'>no online listings found</span>"
            )
        self._hint.setText("Enter trade · 1-9 copy whisper · W wiki · B poe2db · Esc/✕")
        self._url = url
        self._item = item
        self._listings = listings
        self._present()

    def show_error(self, message: str) -> None:
        self._title.setStyleSheet(
            f"font-weight: bold; font-size: 15px; color: {theme.DANGER};"
        )
        self._title.setText("Price check failed")
        self._subtitle.setText("")
        self._band.hide()
        self._mods.hide()
        self._sep.hide()
        self._body.setText(f"<span style='color:{theme.DANGER}'>{message}</span>")
        self._hint.setText("Drag to move  ·  Esc / ✕ to close")
        self._present()

    # -- header helpers -----------------------------------------------------

    def _set_header(self, item: Item) -> None:
        name = item.name or item.base_type or "Unknown item"
        color = theme.rarity_color(item.rarity)
        self._title.setStyleSheet(
            f"font-weight: bold; font-size: 15px; color: {color};"
        )
        self._title.setText(name)
        self._subtitle.setText(self._meta_text(item))

    @staticmethod
    def _meta_text(item: Item) -> str:
        parts: list[str] = []
        if item.base_type and item.base_type != item.name:
            parts.append(item.base_type)
        if item.rarity:
            parts.append(item.rarity)
        if item.item_level:
            parts.append(f"ilvl {item.item_level}")
        return "    ·    ".join(parts)

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
