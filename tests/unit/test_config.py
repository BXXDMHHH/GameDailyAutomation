from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from game_daily_automation.config.loader import (
    ConfigFileNotFoundError, ConfigFormatError, ConfigValidationError, load_config,
)


class ConfigLoaderTests(unittest.TestCase):
    def test_loads_project_settings_and_tool_arguments(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "settings.json"
            path.write_text(json.dumps({
                "schedule": {"time": "17:00"},
                "execution": {"retry_max_attempts": 2, "retry_delay_seconds": 75},
                "storage": {"database_path": "state.sqlite3", "log_directory": "logs"},
                "games": {
                    "bettergi": {
                        "executable": "C:/Tools/BetterGI.exe",
                        "arguments": ["--verified-arg"],
                        "version_arguments": ["--verified-version-arg"],
                    },
                    "march7th": {"executable": "C:/Tools/m7a.exe"},
                },
            }), encoding="utf-8")
            config = load_config(path)
            self.assertEqual(config.schedule.time, "17:00")
            self.assertEqual(config.execution.retry_max_attempts, 2)
            self.assertEqual(config.execution.retry_delay_seconds, 75)
            self.assertEqual(config.storage.database_path, "state.sqlite3")
            self.assertEqual(config.bettergi.arguments, ("--verified-arg",))
            self.assertEqual(
                config.bettergi.version_arguments, ("--verified-version-arg",)
            )
            self.assertEqual(config.march7th.arguments, ())

    def test_missing_file_has_clear_error(self) -> None:
        with self.assertRaisesRegex(ConfigFileNotFoundError, "not found"):
            load_config("missing-settings.json")

    def test_invalid_json_has_line_and_column(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "broken.json"
            path.write_text('{"schedule": ', encoding="utf-8")
            with self.assertRaisesRegex(ConfigFormatError, "line"):
                load_config(path)

    def test_invalid_schedule_time_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "settings.json"
            path.write_text(json.dumps({"schedule": {"time": "25:90"}}), encoding="utf-8")
            with self.assertRaisesRegex(ConfigValidationError, "HH:MM"):
                load_config(path)

    def test_retry_limit_cannot_change_project_requirement(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "settings.json"
            path.write_text(
                json.dumps({"execution": {"retry_max_attempts": 3}}), encoding="utf-8"
            )
            with self.assertRaisesRegex(ConfigValidationError, "must remain 2"):
                load_config(path)


if __name__ == "__main__":
    unittest.main()
