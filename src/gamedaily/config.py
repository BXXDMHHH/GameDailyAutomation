"""JSON configuration loading and validation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from gamedaily.exceptions import ConfigurationError


class ConfigError(ConfigurationError):
    """Base class for configuration loading errors."""


class ConfigFileNotFoundError(ConfigError):
    """Raised when the requested configuration file does not exist."""


class ConfigFormatError(ConfigError):
    """Raised when the configuration file is not valid JSON."""


class ConfigValidationError(ConfigError):
    """Raised when valid JSON does not match the expected schema."""


@dataclass(frozen=True, slots=True)
class LoggingConfig:
    level: str = "INFO"
    file: str = "logs/gamedaily.log"


@dataclass(frozen=True, slots=True)
class RetryConfig:
    interval_seconds: int = 60
    max_attempts: int = 2


@dataclass(frozen=True, slots=True)
class PathsConfig:
    data_dir: str = "data"
    logs_dir: str = "logs"


@dataclass(frozen=True, slots=True)
class AppConfig:
    logging: LoggingConfig
    retry: RetryConfig
    paths: PathsConfig
    base_dir: Path

    @property
    def log_file_path(self) -> Path:
        return _resolve_path(self.base_dir, self.logging.file)

    @property
    def data_dir_path(self) -> Path:
        return _resolve_path(self.base_dir, self.paths.data_dir)

    @property
    def logs_dir_path(self) -> Path:
        return _resolve_path(self.base_dir, self.paths.logs_dir)


def _resolve_path(base_dir: Path, value: str) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else (base_dir / path).resolve()


def _require_object(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ConfigValidationError(f"'{name}' must be a JSON object.")
    return value


def _reject_unknown_keys(data: dict[str, Any], allowed: set[str], section: str) -> None:
    unknown = sorted(set(data) - allowed)
    if unknown:
        raise ConfigValidationError(
            f"Unknown key(s) in '{section}': {', '.join(unknown)}."
        )


def _string(data: dict[str, Any], key: str, default: str, section: str) -> str:
    value = data.get(key, default)
    if not isinstance(value, str) or not value.strip():
        raise ConfigValidationError(f"'{section}.{key}' must be a non-empty string.")
    return value


def _positive_int(data: dict[str, Any], key: str, default: int, section: str) -> int:
    value = data.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ConfigValidationError(f"'{section}.{key}' must be a positive integer.")
    return value


def load_config(config_path: str | Path) -> AppConfig:
    """Load JSON settings and resolve relative paths from the project root."""
    path = Path(config_path).expanduser()
    if not path.is_file():
        raise ConfigFileNotFoundError(f"Configuration file not found: {path}")

    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise ConfigFormatError(
            f"Invalid JSON in '{path}' at line {exc.lineno}, "
            f"column {exc.colno}: {exc.msg}"
        ) from exc
    except UnicodeDecodeError as exc:
        raise ConfigFormatError(f"Configuration file is not valid UTF-8: {path}") from exc

    root = _require_object(raw, "root")
    _reject_unknown_keys(root, {"logging", "retry", "paths"}, "root")

    logging_data = _require_object(root.get("logging", {}), "logging")
    retry_data = _require_object(root.get("retry", {}), "retry")
    paths_data = _require_object(root.get("paths", {}), "paths")
    _reject_unknown_keys(logging_data, {"level", "file"}, "logging")
    _reject_unknown_keys(retry_data, {"interval_seconds", "max_attempts"}, "retry")
    _reject_unknown_keys(paths_data, {"data_dir", "logs_dir"}, "paths")

    level = _string(logging_data, "level", "INFO", "logging").upper()
    if level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        raise ConfigValidationError(
            "'logging.level' must be DEBUG, INFO, WARNING, ERROR, or CRITICAL."
        )

    logging_config = LoggingConfig(
        level=level,
        file=_string(logging_data, "file", "logs/gamedaily.log", "logging"),
    )
    retry = RetryConfig(
        interval_seconds=_positive_int(retry_data, "interval_seconds", 60, "retry"),
        max_attempts=_positive_int(retry_data, "max_attempts", 2, "retry"),
    )
    paths = PathsConfig(
        data_dir=_string(paths_data, "data_dir", "data", "paths"),
        logs_dir=_string(paths_data, "logs_dir", "logs", "paths"),
    )

    resolved_path = path.resolve()
    base_dir = (
        resolved_path.parent.parent
        if resolved_path.parent.name.lower() == "config"
        else resolved_path.parent
    )
    return AppConfig(logging_config, retry, paths, base_dir)
