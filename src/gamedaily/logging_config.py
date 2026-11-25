"""Centralized console and UTF-8 file logging."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from gamedaily.config import AppConfig

LOGGER_NAME = "gamedaily"


def configure_logging(config: AppConfig) -> logging.Logger:
    """Configure application logging; repeated calls replace owned handlers."""
    config.logs_dir_path.mkdir(parents=True, exist_ok=True)
    config.log_file_path.parent.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(getattr(logging, config.logging.level))
    logger.propagate = False

    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
        handler.close()

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    console_handler = logging.StreamHandler()
    console_handler.setLevel(getattr(logging, config.logging.level))
    console_handler.setFormatter(formatter)

    file_handler = RotatingFileHandler(
        config.log_file_path, maxBytes=5 * 1024 * 1024,
        backupCount=3, encoding="utf-8"
    )
    file_handler.setLevel(getattr(logging, config.logging.level))
    file_handler.setFormatter(formatter)

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    return logger
