"""Centralized logger for LogHetero — every module should obtain a logger via ``get_logger``."""

from __future__ import annotations

import logging
import sys
from logging import Logger

_FMT = "%(asctime)s [%(levelname).1s] %(name)s: %(message)s"
_DATEFMT = "%Y-%m-%d %H:%M:%S"


def get_logger(name: str = "loghetero", level: int = logging.INFO) -> Logger:
    """Get (or create) a logger that writes to stdout with a consistent format.

    Calling repeatedly with the same ``name`` returns the same instance and
    does not duplicate handlers.
    """
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(_FMT, datefmt=_DATEFMT))
    logger.addHandler(handler)
    logger.setLevel(level)
    logger.propagate = False
    return logger
