from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from gamedaily.config import (
    ConfigFileNotFoundError, ConfigFormatError, ConfigValidationError, load_config
)


class LoadConfigTests(unittest.TestCase):
    def test_loads_settings_and_resolves_project_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_dir = root / "config"
            config_dir.mkdir()
            config_file = config_dir / "config.json"
            config_file.write_text(
                json.dumps({"logging": {"level": "debug"}}), encoding="utf-8"
            )
            config = load_config(config_file)
            self.assertEqual(config.logging.level, "DEBUG")
            self.assertEqual(config.retry.interval_seconds, 60)
            self.assertEqual(config.retry.max_attempts, 2)
            self.assertEqual(config.log_file_path, root / "logs" / "gamedaily.log")

    def test_missing_file_has_clear_error(self) -> None:
        with self.assertRaisesRegex(ConfigFileNotFoundError, "not found"):
            load_config("does-not-exist.json")

    def test_invalid_json_has_line_and_column(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_file = Path(temp_dir) / "broken.json"
            config_file.write_text('{"logging": ', encoding="utf-8")
            with self.assertRaisesRegex(ConfigFormatError, "line"):
                load_config(config_file)

    def test_invalid_value_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_file = Path(temp_dir) / "config.json"
            config_file.write_text(
                json.dumps({"retry": {"interval_seconds": 0}}), encoding="utf-8"
            )
            with self.assertRaisesRegex(ConfigValidationError, "positive integer"):
                load_config(config_file)

    def test_retry_attempt_limit_cannot_be_overridden(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_file = Path(temp_dir) / "config.json"
            config_file.write_text(
                json.dumps({"retry": {"max_attempts": 5}}), encoding="utf-8"
            )
            with self.assertRaisesRegex(ConfigValidationError, "Unknown key"):
                load_config(config_file)

    def test_unknown_key_is_rejected_to_catch_typos(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_file = Path(temp_dir) / "config.json"
            config_file.write_text(json.dumps({"retrys": {}}), encoding="utf-8")
            with self.assertRaisesRegex(ConfigValidationError, "Unknown key"):
                load_config(config_file)


if __name__ == "__main__":
    unittest.main()
