"""Command-line argument definitions."""

from __future__ import annotations

import argparse
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="game-daily-automation",
        description="Game Daily Automation foundation; game execution is not enabled yet.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config/settings.json"),
        help="JSON settings file (default: config/settings.json).",
    )
    return parser
