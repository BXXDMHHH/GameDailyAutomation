"""Centralized console and UTF-8 rotating file logging."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from game_daily_automation.config.loader import AppConfig

LOGGER_NAME = "game_daily_automation"


def configure_logging(config: AppConfig) -> logging.Logger:
    """Initialize console and file handlers without duplicating them."""
    log_directory = config.storage.log_directory_path
    log_directory.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
        handler.close()

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    console = logging.StreamHandler()
    console.setFormatter(formatter)
    file_handler = RotatingFileHandler(
        log_directory / "gamedaily.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(console)
    logger.addHandler(file_handler)
    return logger
