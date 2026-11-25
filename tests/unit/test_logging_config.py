from __future__ import annotations

import io
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
        logger = logging.getLogger(LOGGER_NAME)
        for handler in logger.handlers[:]:
            logger.removeHandler(handler)
            handler.close()

    def test_writes_to_console_and_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_file = Path(temp_dir) / "settings.json"
            config_file.write_text(
                '{"storage":{"log_directory":"' + str(Path(temp_dir) / "logs") + '"}}',
                encoding="utf-8",
            )
            config = load_config(config_file)
            console = io.StringIO()
            with patch("sys.stderr", console):
                logger = configure_logging(config)
                logger.info("foundation-test-message")
                for handler in logger.handlers:
                    handler.flush()

            self.assertIn("foundation-test-message", console.getvalue())
            log_file = Path(temp_dir) / "logs" / "gamedaily.log"
            self.assertTrue(log_file.exists())
            self.assertIn("foundation-test-message", log_file.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
