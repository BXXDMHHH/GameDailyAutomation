"""Small, dependency-free domain data models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class Game(StrEnum):
    GENSHIN_IMPACT = "genshin_impact"
    HONKAI_STAR_RAIL = "honkai_star_rail"


class ExecutionStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    UNKNOWN = "unknown"
    INTERRUPTED = "interrupted"


@dataclass(frozen=True, slots=True)
class ExecutionAttempt:
    game: Game
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
