"""Shared game-adapter contract; contains no infrastructure dependencies."""

from __future__ import annotations

from typing import Protocol

from game_daily_automation.domain.models import (
    AdapterAvailability, AdapterExecutionResult, ProcessResult,
)
from game_daily_automation.domain.enums import GameKey


class GameAdapter(Protocol):
    """Port implemented independently by each third-party tool adapter."""

    @property
    def game_key(self) -> GameKey: ...

    def check_available(self) -> AdapterAvailability:
        """Check configured executable path and optional configured version probe."""
        ...

    def execute_daily(self) -> AdapterExecutionResult:
        """Run the user-verified daily-task argument vector."""
        ...

    def identify_result(self, process_result: ProcessResult) -> AdapterExecutionResult:
        """Classify a process result using verified tool-specific evidence."""
        ...
