"""
Logging utilities for the arbitrage bot.

The module configures structured logging with console + rotating file handlers.
All modules import `get_logger` to obtain component-specific loggers.
"""

from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path
from typing import Optional

from src.config.settings import settings


_LOGGERS = {}


def _ensure_log_dir() -> Path:
    settings.log_dir.mkdir(parents=True, exist_ok=True)
    return settings.log_dir


def get_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    if name in _LOGGERS:
        return _LOGGERS[name]

    log_dir = _ensure_log_dir()
    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.propagate = False

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s", "%Y-%m-%d %H:%M:%S"
    )

    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    logger.addHandler(sh)

    fh = logging.handlers.TimedRotatingFileHandler(
        log_dir / "bot.log", when="midnight", backupCount=7, encoding="utf-8"
    )
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    _LOGGERS[name] = logger
    return logger


def set_global_level(level: int) -> None:
    for logger in _LOGGERS.values():
        logger.setLevel(level)






