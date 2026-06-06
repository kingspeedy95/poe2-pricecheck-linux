"""Tests for log file setup."""

import importlib
import logging


def test_setup_logging_writes_to_state_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    import poe2price.logsetup as logsetup
    importlib.reload(logsetup)  # pick up the patched env and reset _configured

    logger = logsetup.setup_logging()
    logger.info("hello from test")
    for handler in logger.handlers:
        handler.flush()

    log_file = tmp_path / "poe2-pricecheck" / "poe2price.log"
    assert log_file.exists()
    assert "hello from test" in log_file.read_text()


def test_setup_logging_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    import poe2price.logsetup as logsetup
    importlib.reload(logsetup)

    logger = logsetup.setup_logging()
    count = len(logger.handlers)
    logsetup.setup_logging()  # second call must not add another handler
    assert len(logger.handlers) == count


def teardown_module(module):
    # Reset to a clean logsetup for the rest of the suite.
    import poe2price.logsetup as logsetup
    importlib.reload(logsetup)
    logger = logging.getLogger("poe2price")
    logger.handlers.clear()
