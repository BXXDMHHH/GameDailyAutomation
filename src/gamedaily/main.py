"""Application entry point for the project foundation."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from gamedaily.config import ConfigError, load_config
from gamedaily.logging_config import configure_logging


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gamedaily",
        description="Game Daily Automation foundation (no game tasks are run yet).",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config/config.json"),
        help="Path to the JSON configuration file (default: config/config.json).",
    )
    return parser


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
