"""Dependency-free domain and adapter result models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from game_daily_automation.domain.enums import (
    AdapterExecutionStatus, ExecutionStatus, GameKey,
)


@dataclass(frozen=True, slots=True)
class ProcessResult:
    """Transport-neutral outcome captured by the process boundary."""

    started: bool
    command: tuple[str, ...]
    return_code: int | None
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False
    start_error: str | None = None


@dataclass(frozen=True, slots=True)
class ExecutionAttempt:
    game: GameKey
    attempt_number: int
    status: ExecutionStatus
    started_at: datetime | None = None
    finished_at: datetime | None = None
    detail: str | None = None

    def __post_init__(self) -> None:
        if self.attempt_number < 1:
            raise ValueError("attempt_number must be at least 1")
        if self.finished_at is not None and self.started_at is None:
            raise ValueError("finished_at cannot be set when started_at is missing")
        if self.started_at and self.finished_at and self.finished_at < self.started_at:
            raise ValueError("finished_at cannot be earlier than started_at")


@dataclass(frozen=True, slots=True)
class AdapterAvailability:
    game: GameKey
    executable_path: str
    executable_exists: bool
    configured: bool
    version_probe_configured: bool
    version_probe_return_code: int | None = None
    version_output: str = ""
    error: str | None = None

    @property
    def available(self) -> bool:
        return self.configured and self.executable_exists and self.error is None


@dataclass(frozen=True, slots=True)
class AdapterExecutionResult:
    game: GameKey
    status: AdapterExecutionStatus
    return_code: int | None = None
    stdout: str = ""
    stderr: str = ""
    detail: str | None = None
