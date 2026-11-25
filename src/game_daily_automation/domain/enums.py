"""Domain enumerations."""

from enum import StrEnum


class GameKey(StrEnum):
    BETTERGI = "bettergi"
    MARCH7TH = "march7th"


class ExecutionStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    UNKNOWN = "unknown"
    INTERRUPTED = "interrupted"
