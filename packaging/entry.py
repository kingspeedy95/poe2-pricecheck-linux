"""Frozen-build entry point.

PyInstaller can't run ``poe2price/__main__.py`` directly because of its relative
imports, so this thin wrapper calls the real entry function as a package import.
"""

from poe2price.__main__ import main

if __name__ == "__main__":
    raise SystemExit(main())
