"""Tests for the single-instance lock."""

import subprocess
import sys

from poe2price.singleton import acquire_single_instance_lock


def test_second_instance_is_blocked(tmp_path, monkeypatch):
    # Point the lock at an isolated dir so tests never collide with a real run.
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))

    handle = acquire_single_instance_lock()
    assert handle is not None, "first instance should get the lock"

    # A separate process must not be able to take the lock while we hold it.
    code = (
        "from poe2price.singleton import acquire_single_instance_lock as a;"
        "print('got' if a() else 'blocked')"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True, text=True,
        env={**__import__("os").environ, "XDG_RUNTIME_DIR": str(tmp_path)},
    )
    assert result.stdout.strip() == "blocked", result.stderr

    # After we release, a new instance can acquire it again.
    handle.close()
    result2 = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True, text=True,
        env={**__import__("os").environ, "XDG_RUNTIME_DIR": str(tmp_path)},
    )
    assert result2.stdout.strip() == "got", result2.stderr
