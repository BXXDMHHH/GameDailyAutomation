from __future__ import annotations

import io
import json
import logging
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from game_daily_automation.infrastructure.logging_config import LOGGER_NAME
from game_daily_automation.main import main


class MainTests(unittest.TestCase):
    def test_missing_config_returns_nonzero(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            missing = Path(temp_dir) / "missing.json"
            with patch("sys.stderr", io.StringIO()) as stderr:
                result = main(["--config", str(missing)])
            self.assertEqual(result, 2)
            self.assertIn("not found", stderr.getvalue())

    def test_check_session_does_not_run_tasks(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_file = Path(temp_dir) / "settings.json"
            config_file.write_text(json.dumps({"storage": {"log_directory": str(Path(temp_dir) / "logs")}}), encoding="utf-8")
            from game_daily_automation.system.windows_session import SessionStatus, SessionState
            try:
                with patch("game_daily_automation.main.inspect_windows_session",
                           return_value=SessionStatus(SessionState.LOCKED, 1, "Winlogon")):
                    with patch("sys.stdout", io.StringIO()):
                        result = main(["--config", str(config_file), "--check-session"])
                self.assertEqual(result, 3)
            finally:
                logger = logging.getLogger(LOGGER_NAME)
                for handler in logger.handlers[:]:
                    logger.removeHandler(handler)
                    handler.close()

    def test_valid_config_starts_without_running_game_tasks_on_non_windows(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_file = root / "settings.json"
            config_file.write_text(json.dumps({"storage": {"log_directory": str(root / "logs")}}), encoding="utf-8")
            try:
                with patch("game_daily_automation.main.sys.platform", "linux"):
                    with patch("sys.stderr", io.StringIO()):
                        result = main(["--config", str(config_file)])
                self.assertEqual(result, 3)
                self.assertTrue((root / "logs" / "gamedaily.log").exists())
            finally:
                logger = logging.getLogger(LOGGER_NAME)
                for handler in logger.handlers[:]:
                    logger.removeHandler(handler)
                    handler.close()


if __name__ == "__main__":
    unittest.main()
