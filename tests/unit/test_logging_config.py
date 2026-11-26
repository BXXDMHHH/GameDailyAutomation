from __future__ import annotations

import io
import json
import logging
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from game_daily_automation.config.loader import load_config
from game_daily_automation.infrastructure.logging_config import (
    LOGGER_NAME, configure_logging,
)


class LoggingConfigTests(unittest.TestCase):
    def tearDown(self) -> None:
        self._close_logger_handlers()

    @staticmethod
    def _close_logger_handlers() -> None:
        logger = logging.getLogger(LOGGER_NAME)
        for handler in logger.handlers[:]:
            logger.removeHandler(handler)
            handler.close()

    def test_writes_to_console_and_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            log_directory = Path(temp_dir) / "logs"
            config_file = Path(temp_dir) / "settings.json"
            config_file.write_text(
                json.dumps({"storage": {"log_directory": str(log_directory)}}),
                encoding="utf-8",
            )
            config = load_config(config_file)
            console = io.StringIO()
            try:
                with patch("sys.stderr", console):
                    logger = configure_logging(config)
                    logger.info("foundation-test-message")
                    for handler in logger.handlers:
                        handler.flush()

                self.assertIn("foundation-test-message", console.getvalue())
                log_file = log_directory / "gamedaily.log"
                self.assertTrue(log_file.exists())
                self.assertIn(
                    "foundation-test-message",
                    log_file.read_text(encoding="utf-8"),
                )
            finally:
                # Windows cannot remove a temporary directory while its log
                # file is still open. Close handlers before TemporaryDirectory
                # performs its cleanup (tearDown runs too late for this).
                self._close_logger_handlers()


if __name__ == "__main__":
    unittest.main()
