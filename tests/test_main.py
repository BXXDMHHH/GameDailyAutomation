from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from gamedaily.main import main


class MainTests(unittest.TestCase):
    def test_missing_config_returns_nonzero(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            missing = Path(temp_dir) / "missing.json"
            self.assertEqual(main(["--config", str(missing)]), 2)


if __name__ == "__main__":
    unittest.main()
