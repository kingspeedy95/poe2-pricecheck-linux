"""Single-instance guard.

Uses an advisory ``flock`` on a lock file. The lock is held for as long as the
process lives and is released automatically by the kernel when the process
exits (even on a crash), so there are no stale-PID problems. A second instance
that can't take the lock knows one is already running.
"""

from __future__ import annotations

import fcntl
import os


def _lock_path() -> str:
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    if runtime and os.path.isdir(runtime):
        base = runtime
    else:
        base = os.path.join(
            os.environ.get("XDG_STATE_HOME", os.path.expanduser("~/.local/state")),
            "poe2-pricecheck",
        )
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, "poe2-pricecheck.lock")


def acquire_single_instance_lock():
    """Take the single-instance lock.

    Returns an open file handle (keep a reference to it for the lifetime of the
    process) when we are the only instance, or ``None`` if another instance
    already holds the lock.
    """
    handle = open(_lock_path(), "w")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        return None
    # Stamp our PID for human inspection; the flock is the real guard.
    try:
        handle.truncate(0)
        handle.write(str(os.getpid()))
        handle.flush()
    except OSError:
        pass
    return handle
