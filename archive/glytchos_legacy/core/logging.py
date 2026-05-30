"""
glytchos/core/logging.py
------------------------
Structured console + file logger for the GlitchOS.io pipeline.
Writes "[TIMESTAMP] [LEVEL] [region] message" to both stdout and log file.
No third-party dependencies.
"""

from __future__ import annotations

import sys
import logging
import logging.handlers
from pathlib import Path


_LOGGERS: dict[str, logging.Logger] = {}

_FMT = "[%(asctime)s] [%(levelname)s] [%(region)s] %(message)s"
_DATE_FMT = "%Y-%m-%dT%H:%M:%S"


class _RegionFilter(logging.Filter):
    """Inject 'region' field into every LogRecord."""

    def __init__(self, region_id: str) -> None:
        super().__init__()
        self.region_id = region_id

    def filter(self, record: logging.LogRecord) -> bool:
        record.region = self.region_id  # type: ignore[attr-defined]
        return True


def get_logger(region_id: str, log_path: Path | None = None) -> logging.Logger:
    """
    Return (and cache) a structured logger for *region_id*.

    Parameters
    ----------
    region_id:
        Short region identifier used in log prefix, e.g. "greater_la".
    log_path:
        Path to the log file. If None, logs go to stdout only.
        The parent directory is created if it does not exist.
    """
    if region_id in _LOGGERS:
        return _LOGGERS[region_id]

    logger = logging.getLogger(f"glytchos.{region_id}")
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    region_filter = _RegionFilter(region_id)
    formatter = logging.Formatter(_FMT, datefmt=_DATE_FMT)

    # stdout handler
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setLevel(logging.INFO)
    stdout_handler.setFormatter(formatter)
    stdout_handler.addFilter(region_filter)
    logger.addHandler(stdout_handler)

    # file handler (optional)
    if log_path is not None:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_path, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        file_handler.addFilter(region_filter)
        logger.addHandler(file_handler)

    _LOGGERS[region_id] = logger
    return logger


def clear_logger_cache() -> None:
    """Remove all cached loggers (useful for tests)."""
    _LOGGERS.clear()
