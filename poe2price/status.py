"""Small status toast shown at the bottom-centre of the screen.

Used for non-price feedback such as "Waiting for Path of Exile 2 to start…"
and "Path of Exile 2 detected — running in background.". Frameless, never
steals focus, and auto-hides when asked.
"""

from __future__ import annotations

from pathlib import Path

from PyQt6 import QtCore, QtGui, QtWidgets

_ASSETS = Path(__file__).resolve().parent.parent / "assets"


def app_icon() -> QtGui.QIcon:
    """The application icon, loaded from bundled assets (theme as fallback)."""
    for name in ("png/icon-256.png", "icon.png", "icon.svg"):
        path = _ASSETS / name
        if path.exists():
            return QtGui.QIcon(str(path))
    return QtGui.QIcon.fromTheme("poe2-pricecheck")


class StatusToast(QtWidgets.QWidget):
    """A thin status banner pinned to the bottom-centre of the active screen."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowFlags(
            QtCore.Qt.WindowType.FramelessWindowHint
            | QtCore.Qt.WindowType.WindowStaysOnTopHint
            | QtCore.Qt.WindowType.Tool
        )
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_ShowWithoutActivating)

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(20, 16, 24, 16)
        layout.setSpacing(14)

        self._icon = QtWidgets.QLabel()
        self._icon.setPixmap(
            app_icon().pixmap(QtCore.QSize(40, 40))
        )
        self._icon.setFixedSize(40, 40)
        self._icon.setScaledContents(True)
        layout.addWidget(self._icon, 0, QtCore.Qt.AlignmentFlag.AlignVCenter)

        self._label = QtWidgets.QLabel()
        self._label.setStyleSheet("color: #eee; font-size: 15px;")
        layout.addWidget(self._label, 1, QtCore.Qt.AlignmentFlag.AlignVCenter)

        self.setStyleSheet(
            "StatusToast { background: #1b1b1f; border: 1px solid #555; "
            "border-radius: 12px; }"
        )

        self._hide_timer = QtCore.QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self.hide)

    def show_message(self, text: str, *, auto_hide_ms: int | None = None) -> None:
        """Show *text*; if *auto_hide_ms* is given, hide after that delay."""
        self._hide_timer.stop()
        self._label.setText(text)
        self.adjustSize()
        self._reposition()
        self.show()
        self.raise_()
        if auto_hide_ms is not None:
            self._hide_timer.start(auto_hide_ms)

    def _reposition(self) -> None:
        """Pin to the bottom-centre of the screen under the cursor."""
        screen = (
            QtWidgets.QApplication.screenAt(QtGui.QCursor.pos())
            or QtWidgets.QApplication.primaryScreen()
        )
        area = screen.availableGeometry()
        x = area.left() + (area.width() - self.width()) // 2
        y = area.bottom() - self.height() - 80  # a little above the taskbar
        self.move(x, y)
