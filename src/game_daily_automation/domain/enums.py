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


class AdapterExecutionStatus(StrEnum):
    NOT_CONFIGURED = "not_configured"
    START_FAILED = "start_failed"
    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"
    UNKNOWN = "unknown"
