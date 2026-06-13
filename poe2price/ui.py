"""A small frameless popup that shows the price result near the cursor.

The window is draggable (click anywhere and drag), remembers where it was when
last closed, has an ✕ button in the corner, and is clamped to stay fully on a
single monitor so it never drifts off the edge onto another screen.

For rares/magics (and white bases) the popup is *interactive*: each parsed mod
becomes a checkbox row with an editable min/max, plus item-level and rarity
toggles, and a Search button re-runs the trade query with the refined filters —
the same idea as Exiled Exchange's rare-check panel.
"""

from __future__ import annotations

from PyQt6 import QtCore, QtGui, QtWidgets

from . import theme
from .links import poe2db_url, wiki_url
from .modview import mods_html
from .parser import Item
from .stats import StatFilter
from .trade import Listing, SearchSpec, summarize


def _num_text(value: float | None) -> str:
    """Render a filter min/max for an edit box ('' when unset)."""
    if value is None:
        return ""
    return str(int(value)) if value == int(value) else str(round(value, 2))


def _parse_num(text: str) -> float | None:
    """Parse an edit box back to a number (None when blank/invalid)."""
    text = text.strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


class _FilterRow(QtWidgets.QWidget):
    """One mod: a checkbox (include in search) + editable min/max boxes."""

    def __init__(self, filt: StatFilter) -> None:
        super().__init__()
        self.filt = filt

        row = QtWidgets.QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(5)

        self.check = QtWidgets.QCheckBox(filt.label)
        self.check.setChecked(filt.enabled)
        color = theme.MOD if filt.kind in ("explicit", "crafted", "fractured") else theme.TEXT_DIM
        self.check.setStyleSheet(f"QCheckBox {{ color: {color}; font-size: 11px; }}")

        self.min_edit = QtWidgets.QLineEdit(_num_text(filt.min))
        self.max_edit = QtWidgets.QLineEdit(_num_text(filt.max))
        for edit, placeholder in ((self.min_edit, "min"), (self.max_edit, "max")):
            edit.setPlaceholderText(placeholder)
            edit.setFixedWidth(46)
            edit.setStyleSheet(
                f"QLineEdit {{ background: {theme.BG_PANEL}; color: {theme.TEXT}; "
                f"border: 1px solid {theme.BORDER}; border-radius: 4px; "
                f"padding: 1px 3px; font-size: 11px; }}"
            )

        row.addWidget(self.check, 1)
        row.addWidget(self.min_edit)
        row.addWidget(self.max_edit)

    def sync(self) -> None:
        """Write the row's widgets back into its :class:`StatFilter`."""
        self.filt.enabled = self.check.isChecked()
        self.filt.min = _parse_num(self.min_edit.text())
        self.filt.max = _parse_num(self.max_edit.text())


class PriceWindow(QtWidgets.QWidget):
    # Emitted when the user presses Search; carries the refined SearchSpec.
    search_requested = QtCore.pyqtSignal(object)

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
        self._spec: SearchSpec | None = None  # editable search, if any
        self._summary: str = ""               # plan description for the band
        self._rows: list[_FilterRow] = []

        self.setMinimumWidth(320)
        self.setMaximumWidth(520)
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
        self._subtitle.setStyleSheet(f"color: {theme.TEXT_DIM}; font-size: 11px;")
        self._layout.addWidget(self._subtitle)

        # -- price band (raised panel) --------------------------------------
        self._price = QtWidgets.QLabel()
        self._price.setStyleSheet(
            f"color: {theme.GOLD}; font-size: 18px; font-weight: bold;"
        )
        self._price_sub = QtWidgets.QLabel()
        self._price_sub.setWordWrap(True)
        self._price_sub.setStyleSheet(f"color: {theme.TEXT_DIM}; font-size: 10px;")
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

        # -- read-only mods (uniques / white bases without editable filters) -
        self._mods = QtWidgets.QLabel()
        self._mods.setTextFormat(QtCore.Qt.TextFormat.RichText)
        self._mods.setWordWrap(True)
        self._mods.setStyleSheet("font-size: 11px;")
        self._layout.addWidget(self._mods)

        # -- interactive filter panel ---------------------------------------
        self._filter_box = self._build_filter_box()
        self._layout.addWidget(self._filter_box)

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

    # -- filter panel construction -----------------------------------------

    def _build_filter_box(self) -> QtWidgets.QWidget:
        box = QtWidgets.QWidget()
        outer = QtWidgets.QVBoxLayout(box)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(5)

        # Per-mod checkbox rows go here (rebuilt on each item).
        self._stats_container = QtWidgets.QVBoxLayout()
        self._stats_container.setContentsMargins(0, 0, 0, 0)
        self._stats_container.setSpacing(3)
        outer.addLayout(self._stats_container)

        # Item-level toggle + value.
        self._ilvl_row = QtWidgets.QWidget()
        ilvl_lay = QtWidgets.QHBoxLayout(self._ilvl_row)
        ilvl_lay.setContentsMargins(0, 0, 0, 0)
        ilvl_lay.setSpacing(5)
        self._ilvl_check = QtWidgets.QCheckBox("Item level ≥")
        self._ilvl_check.setStyleSheet(f"QCheckBox {{ color: {theme.TEXT_DIM}; font-size: 11px; }}")
        self._ilvl_edit = QtWidgets.QLineEdit()
        self._ilvl_edit.setFixedWidth(46)
        self._ilvl_edit.setValidator(QtGui.QIntValidator(0, 100, self))
        self._ilvl_edit.setStyleSheet(
            f"QLineEdit {{ background: {theme.BG_PANEL}; color: {theme.TEXT}; "
            f"border: 1px solid {theme.BORDER}; border-radius: 4px; "
            f"padding: 1px 3px; font-size: 11px; }}"
        )
        ilvl_lay.addWidget(self._ilvl_check)
        ilvl_lay.addWidget(self._ilvl_edit)
        ilvl_lay.addStretch(1)
        outer.addWidget(self._ilvl_row)

        # Rarity toggle (white-base / normal-only).
        self._rarity_check = QtWidgets.QCheckBox("Normal (white) bases only")
        self._rarity_check.setStyleSheet(f"QCheckBox {{ color: {theme.TEXT_DIM}; font-size: 11px; }}")
        outer.addWidget(self._rarity_check)

        # Search button + result count.
        action = QtWidgets.QHBoxLayout()
        action.setContentsMargins(0, 0, 0, 0)
        action.setSpacing(8)
        self._search_btn = QtWidgets.QPushButton("🔍 Search")
        self._search_btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self._search_btn.setStyleSheet(
            f"QPushButton {{ background: {theme.BG_PANEL}; color: {theme.GOLD}; "
            f"border: 1px solid {theme.BORDER}; border-radius: 5px; "
            f"padding: 3px 12px; font-weight: bold; font-size: 11px; }}"
            f"QPushButton:hover {{ border-color: {theme.GOLD_DIM}; }}"
            f"QPushButton:disabled {{ color: {theme.TEXT_FAINT}; }}"
        )
        self._search_btn.clicked.connect(self._do_search)
        self._matched = QtWidgets.QLabel("")
        self._matched.setStyleSheet(f"color: {theme.TEXT_DIM}; font-size: 11px;")
        action.addWidget(self._search_btn)
        action.addWidget(self._matched, 1)
        outer.addLayout(action)

        return box

    # -- display ------------------------------------------------------------

    def show_loading(self, item: Item) -> None:
        self._set_header(item)
        self._band.hide()
        self._mods.hide()
        self._filter_box.hide()
        self._sep.hide()
        self._body.setText(
            f"<i style='color:{theme.TEXT_DIM}'>searching the trade API…</i>"
        )
        self._hint.setText("Drag to move  ·  Esc / ✕ to close")
        self._present()

    def show_result(
        self,
        item: Item,
        listings: list[Listing],
        url: str,
        summary: str = "",
        spec: SearchSpec | None = None,
    ) -> None:
        self._set_header(item)
        self._item = item
        self._url = url
        self._spec = spec
        self._summary = summary

        self._render_price(listings)

        if spec is not None and _spec_is_editable(spec):
            self._populate_filters(spec)
            self._filter_box.show()
            self._mods.hide()
        else:
            self._filter_box.hide()
            mods = mods_html(item)
            self._mods.setText(mods)
            self._mods.setVisible(bool(mods))

        self._sep.show()
        self._render_listings(listings)
        self._hint.setText("Enter trade · 1-9 copy whisper · W wiki · B poe2db · Esc/✕")
        self._present()

    def update_listings(self, listings: list[Listing], url: str) -> None:
        """Refresh just the price/listings after a refined re-search."""
        self._url = url
        self._listings = listings
        self._render_price(listings)
        self._render_listings(listings)
        self._search_btn.setEnabled(True)
        self._search_btn.setText("🔍 Search")
        self._present()

    def show_searching(self) -> None:
        """Indicate a refined search is in flight (Search button pressed)."""
        self._search_btn.setEnabled(False)
        self._search_btn.setText("…searching")
        self._matched.setStyleSheet(f"color: {theme.TEXT_DIM}; font-size: 11px;")
        self._matched.setText("searching the trade API…")

    def show_search_error(self, message: str) -> None:
        """A refined-search failure that keeps the filter panel intact."""
        self._search_btn.setEnabled(True)
        self._search_btn.setText("🔍 Search")
        self._matched.setStyleSheet(f"color: {theme.DANGER}; font-size: 11px;")
        self._matched.setText(message)
        self._present()

    def show_error(self, message: str) -> None:
        self._title.setStyleSheet(
            f"font-weight: bold; font-size: 15px; color: {theme.DANGER};"
        )
        self._title.setText("Price check failed")
        self._subtitle.setText("")
        self._band.hide()
        self._mods.hide()
        self._filter_box.hide()
        self._sep.hide()
        self._body.setText(f"<span style='color:{theme.DANGER}'>{message}</span>")
        self._hint.setText("Drag to move  ·  Esc / ✕ to close")
        self._present()

    # -- rendering helpers --------------------------------------------------

    def _render_price(self, listings: list[Listing]) -> None:
        stats = summarize(listings)
        self._price.setText(stats.headline)
        detail = stats.detail
        if self._summary:
            detail = f"{detail}  ·  {self._summary}" if detail else self._summary
        self._price_sub.setText(detail)
        self._band.show()
        self._matched.setStyleSheet(f"color: {theme.TEXT_DIM}; font-size: 11px;")
        self._matched.setText(
            f"{len(listings)} listing" + ("s" if len(listings) != 1 else "")
        )

    def _render_listings(self, listings: list[Listing]) -> None:
        self._listings = listings
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

    def _populate_filters(self, spec: SearchSpec) -> None:
        # Clear any rows from the previous item.
        while self._stats_container.count():
            item = self._stats_container.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)  # remove now (deleteLater is async)
                widget.deleteLater()
        self._rows = []
        for filt in spec.stats:
            row = _FilterRow(filt)
            self._rows.append(row)
            self._stats_container.addWidget(row)

        # Item level: shown whenever the spec knows one (even if off by default).
        has_ilvl = spec.ilvl_min is not None
        self._ilvl_row.setVisible(has_ilvl)
        if has_ilvl:
            self._ilvl_check.setChecked(spec.ilvl_enabled)
            self._ilvl_edit.setText(str(spec.ilvl_min))

        # Rarity (normal-only) toggle: shown only when the base supports it.
        has_rarity = spec.rarity is not None
        self._rarity_check.setVisible(has_rarity)
        if has_rarity:
            self._rarity_check.setChecked(spec.rarity_enabled)

    def _sync_spec_from_ui(self) -> None:
        if self._spec is None:
            return
        for row in self._rows:
            row.sync()
        if self._spec.ilvl_min is not None:
            self._spec.ilvl_enabled = self._ilvl_check.isChecked()
            self._spec.ilvl_min = int(_parse_num(self._ilvl_edit.text()) or self._spec.ilvl_min)
        if self._spec.rarity is not None:
            self._spec.rarity_enabled = self._rarity_check.isChecked()

    def _do_search(self) -> None:
        if self._spec is None:
            return
        self._sync_spec_from_ui()
        self.show_searching()
        self.search_requested.emit(self._spec)

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


def _spec_is_editable(spec: SearchSpec) -> bool:
    """True when the spec has something worth showing interactive controls for."""
    return bool(spec.stats) or spec.ilvl_min is not None or spec.rarity is not None
