"""Shared pytest fixtures.

The UI tests need a ``QApplication`` but no real display, so we force Qt's
offscreen platform plugin before any Qt import creates one.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest


@pytest.fixture(scope="session")
def qapp():
    """A single offscreen QApplication shared across the test session."""
    from PyQt6 import QtWidgets

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    yield app
