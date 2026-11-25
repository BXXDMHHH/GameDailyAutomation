"""Shared application exception hierarchy."""


class GameDailyError(Exception):
    """Base class for expected application errors."""


class ConfigurationError(GameDailyError):
    """Configuration-related error."""


class StatePersistenceError(GameDailyError):
    """Raised when required application state cannot be persisted."""


class ProcessExecutionError(GameDailyError):
    """Raised when an external process cannot be managed safely."""


class SingleInstanceError(GameDailyError):
    """Raised when another application instance is already active."""
