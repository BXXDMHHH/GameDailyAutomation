from __future__ import annotations

import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from game_daily_automation.main import main


class MainTests(unittest.TestCase):
    def test_missing_config_returns_nonzero(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            missing = Path(temp_dir) / "missing.json"
            with patch("sys.stderr", io.StringIO()) as stderr:
                result = main(["--config", str(missing)])
            self.assertEqual(result, 2)
            self.assertIn("not found", stderr.getvalue())

    def test_valid_config_starts_without_running_game_tasks(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_file = root / "settings.json"
            config_file.write_text(
                json.dumps({"storage": {"log_directory": str(root / "logs")}}),
                encoding="utf-8",
            )
            with patch("sys.stderr", io.StringIO()):
                result = main(["--config", str(config_file)])
            self.assertEqual(result, 0)
            self.assertTrue((root / "logs" / "gamedaily.log").exists())


if __name__ == "__main__":
    unittest.main()
