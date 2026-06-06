"""Application logging to a rotating file under the XDG state dir.

Keeping a log makes it possible to debug issues after the fact, especially when
the app is launched from the taskbar with no terminal attached.
"""

from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler

_STATE_DIR = os.path.join(
    os.environ.get("XDG_STATE_HOME", os.path.expanduser("~/.local/state")),
    "poe2-pricecheck",
)
LOG_PATH = os.path.join(_STATE_DIR, "poe2price.log")

_configured = False


def setup_logging(level: int = logging.INFO) -> logging.Logger:
    """Configure the package logger to write to a rotating file. Idempotent."""
    logger = logging.getLogger("poe2price")
    global _configured
    if _configured:
        return logger
    logger.setLevel(level)
    try:
        os.makedirs(_STATE_DIR, exist_ok=True)
        handler: logging.Handler = RotatingFileHandler(
            LOG_PATH, maxBytes=512_000, backupCount=3, encoding="utf-8"
        )
    except OSError:
        handler = logging.NullHandler()
    handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s: %(message)s"
    ))
    logger.addHandler(handler)
    logger.propagate = False
    _configured = True
    return logger


def get_logger(name: str = "poe2price") -> logging.Logger:
    return logging.getLogger(name)
