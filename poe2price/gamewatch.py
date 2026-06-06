"""Detect whether Path of Exile 2 is running.

Pure-Python scan of ``/proc`` — no external tools — so it matches the rest of
the project. Under Steam/Proton the game shows up as several processes whose
command line references ``.../Path of Exile 2/PathOfExileSteam.exe``; the
standalone client is ``PathOfExile.exe``. Both contain the case-insensitive
substring ``pathofexile`` in their cmdline, which is what we match on.
"""

from __future__ import annotations

import glob
import os

# Lower-cased markers searched for in each process's command line. The exe name
# has no spaces, so "pathofexile" matches Steam and standalone variants alike.
_MARKERS = ("pathofexile",)


def cmdline_is_game(cmdline: str) -> bool:
    """Return True if a process *cmdline* looks like Path of Exile 2."""
    lowered = cmdline.lower()
    return any(marker in lowered for marker in _MARKERS)


def is_game_running() -> bool:
    """Return True if a Path of Exile 2 process is currently running."""
    self_pid = os.getpid()
    for cmdline_path in glob.glob("/proc/[0-9]*/cmdline"):
        try:
            pid = int(cmdline_path.split("/", 3)[2])
        except (IndexError, ValueError):
            continue
        if pid == self_pid:
            continue  # never match ourselves
        try:
            with open(cmdline_path, "rb") as fh:
                raw = fh.read()
        except OSError:
            continue  # process vanished or not readable
        cmd = raw.replace(b"\x00", b" ").decode("utf-8", "ignore")
        if cmdline_is_game(cmd):
            return True
    return False
