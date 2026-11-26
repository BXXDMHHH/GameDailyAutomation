"""Command-line argument definitions."""

from __future__ import annotations

import argparse
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="game-daily-automation",
        description="Windows interactive-desktop daily game task scheduler.",
    )
    parser.add_argument(
        "--config", type=Path, default=Path("config/settings.json"),
        help="JSON settings file (default: config/settings.json).",
    )
    parser.add_argument(
        "--check-session", action="store_true",
        help="Inspect the current Windows interactive session and exit without running tasks.",
    )
    return parser
