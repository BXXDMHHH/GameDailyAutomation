from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from game_daily_automation.exceptions import SingleInstanceError
from game_daily_automation.infrastructure.single_instance import SingleInstanceLock


class SingleInstanceLockTests(unittest.TestCase):
    def test_second_lock_is_rejected_until_first_released(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "app.lock"
            first = SingleInstanceLock(path).acquire()
            try:
                with self.assertRaises(SingleInstanceError):
                    SingleInstanceLock(path).acquire()
            finally:
                first.release()
            second = SingleInstanceLock(path).acquire()
            second.release()

    def test_context_manager_releases_lock(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "app.lock"
            with SingleInstanceLock(path):
                with self.assertRaises(SingleInstanceError):
                    SingleInstanceLock(path).acquire()
            with SingleInstanceLock(path):
                pass


if __name__ == "__main__":
    unittest.main()
