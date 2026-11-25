"""JSON settings loader and schema validation."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from game_daily_automation.exceptions import ConfigurationError


class ConfigError(ConfigurationError):
    """Base class for configuration loading errors."""


class ConfigFileNotFoundError(ConfigError):
    """Configuration file is missing."""


class ConfigFormatError(ConfigError):
    """Configuration file is not valid UTF-8 JSON."""


class ConfigValidationError(ConfigError):
    """Configuration values do not match the supported schema."""


@dataclass(frozen=True, slots=True)
class ScheduleConfig:
    time: str = "17:00"
    timezone: str = "local"
    run_on_logon: bool = True
    run_on_unlock: bool = True
    wake_to_run: bool = True


@dataclass(frozen=True, slots=True)
class ExecutionConfig:
    wait_for_unlocked_session: bool = True
    retry_max_attempts: int = 2
    retry_delay_seconds: int = 60


@dataclass(frozen=True, slots=True)
class StorageConfig:
    database_path: str = "%LOCALAPPDATA%/GameDailyAutomation/data.sqlite3"
    log_directory: str = "%LOCALAPPDATA%/GameDailyAutomation/logs"

    @property
    def database_file_path(self) -> Path:
        return Path(os.path.expandvars(self.database_path)).expanduser()

    @property
    def log_directory_path(self) -> Path:
        return Path(os.path.expandvars(self.log_directory)).expanduser()


@dataclass(frozen=True, slots=True)
class GameToolConfig:
    enabled: bool = True
    executable: str = ""
    working_directory: str = ""
    arguments: tuple[str, ...] = ()
    version_arguments: tuple[str, ...] = ()
    timeout_seconds: int = 7200


@dataclass(frozen=True, slots=True)
class AppConfig:
    schedule: ScheduleConfig
    execution: ExecutionConfig
    storage: StorageConfig
    bettergi: GameToolConfig
    march7th: GameToolConfig


def _object(value: Any, section: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ConfigValidationError(f"'{section}' must be a JSON object.")
    return value


def _keys(data: dict[str, Any], allowed: set[str], section: str) -> None:
    unknown = sorted(set(data) - allowed)
    if unknown:
        raise ConfigValidationError(
            f"Unknown key(s) in '{section}': {', '.join(unknown)}."
        )


def _string(data: dict[str, Any], key: str, default: str, section: str) -> str:
    value = data.get(key, default)
    if not isinstance(value, str):
        raise ConfigValidationError(f"'{section}.{key}' must be a string.")
    return value


def _boolean(data: dict[str, Any], key: str, default: bool, section: str) -> bool:
    value = data.get(key, default)
    if not isinstance(value, bool):
        raise ConfigValidationError(f"'{section}.{key}' must be true or false.")
    return value


def _positive_int(data: dict[str, Any], key: str, default: int, section: str) -> int:
    value = data.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ConfigValidationError(f"'{section}.{key}' must be a positive integer.")
    return value


def _string_array(data: dict[str, Any], key: str, section: str) -> tuple[str, ...]:
    value = data.get(key, [])
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ConfigValidationError(f"'{section}.{key}' must be an array of strings.")
    return tuple(value)


def _game_tool(data: dict[str, Any], name: str) -> GameToolConfig:
    section = f"games.{name}"
    _keys(
        data,
        {"enabled", "executable", "working_directory", "arguments",
         "version_arguments", "timeout_seconds"},
        section,
    )
    return GameToolConfig(
        enabled=_boolean(data, "enabled", True, section),
        executable=_string(data, "executable", "", section),
        working_directory=_string(data, "working_directory", "", section),
        arguments=_string_array(data, "arguments", section),
        version_arguments=_string_array(data, "version_arguments", section),
        timeout_seconds=_positive_int(data, "timeout_seconds", 7200, section),
    )


def load_config(config_path: str | Path) -> AppConfig:
    """Load the documented project settings schema from a UTF-8 JSON file."""
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

    root = _object(raw, "root")
    _keys(root, {"schedule", "execution", "storage", "games"}, "root")
    schedule_data = _object(root.get("schedule", {}), "schedule")
    execution_data = _object(root.get("execution", {}), "execution")
    storage_data = _object(root.get("storage", {}), "storage")
    games_data = _object(root.get("games", {}), "games")
    _keys(schedule_data, {"time", "timezone", "run_on_logon", "run_on_unlock", "wake_to_run"}, "schedule")
    _keys(execution_data, {"wait_for_unlocked_session", "retry_max_attempts", "retry_delay_seconds"}, "execution")
    _keys(storage_data, {"database_path", "log_directory"}, "storage")
    _keys(games_data, {"bettergi", "march7th"}, "games")

    schedule_time = _string(schedule_data, "time", "17:00", "schedule")
    if (
        len(schedule_time) != 5
        or schedule_time[2] != ":"
        or not schedule_time[:2].isdigit()
        or not schedule_time[3:].isdigit()
        or int(schedule_time[:2]) > 23
        or int(schedule_time[3:]) > 59
    ):
        raise ConfigValidationError("'schedule.time' must use 24-hour HH:MM format.")

    schedule = ScheduleConfig(
        time=schedule_time,
        timezone=_string(schedule_data, "timezone", "local", "schedule"),
        run_on_logon=_boolean(schedule_data, "run_on_logon", True, "schedule"),
        run_on_unlock=_boolean(schedule_data, "run_on_unlock", True, "schedule"),
        wake_to_run=_boolean(schedule_data, "wake_to_run", True, "schedule"),
    )
    attempts = _positive_int(execution_data, "retry_max_attempts", 2, "execution")
    if attempts != 2:
        raise ConfigValidationError(
            "'execution.retry_max_attempts' must remain 2 per project requirements."
        )
    execution = ExecutionConfig(
        wait_for_unlocked_session=_boolean(
            execution_data, "wait_for_unlocked_session", True, "execution"
        ),
        retry_max_attempts=attempts,
        retry_delay_seconds=_positive_int(
            execution_data, "retry_delay_seconds", 60, "execution"
        ),
    )
    storage = StorageConfig(
        database_path=_string(
            storage_data, "database_path",
            "%LOCALAPPDATA%/GameDailyAutomation/data.sqlite3", "storage"
        ),
        log_directory=_string(
            storage_data, "log_directory",
            "%LOCALAPPDATA%/GameDailyAutomation/logs", "storage"
        ),
    )
    bettergi = _game_tool(_object(games_data.get("bettergi", {}), "games.bettergi"), "bettergi")
    march7th = _game_tool(_object(games_data.get("march7th", {}), "games.march7th"), "march7th")
    return AppConfig(schedule, execution, storage, bettergi, march7th)
