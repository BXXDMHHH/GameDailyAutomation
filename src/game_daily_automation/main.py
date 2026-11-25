"""Application bootstrap; does not execute game tasks."""

from __future__ import annotations

import sys
from collections.abc import Sequence

from game_daily_automation.cli import build_parser
from game_daily_automation.config.loader import ConfigError, load_config
from game_daily_automation.infrastructure.logging_config import configure_logging


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        config = load_config(args.config)
        logger = configure_logging(config)
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"Unable to initialize logging: {exc}", file=sys.stderr)
        return 2

    logger.info("Game Daily Automation foundation started.")
    logger.info("Configuration loaded from: %s", args.config.resolve())
    logger.info("No game tasks are started by this foundation entry point.")
    return 0
