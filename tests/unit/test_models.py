from __future__ import annotations

import unittest
from datetime import datetime, timezone

from game_daily_automation.domain.enums import ExecutionStatus, GameKey
from game_daily_automation.domain.models import ExecutionAttempt


class DomainModelTests(unittest.TestCase):
    def test_attempt_accepts_valid_state(self) -> None:
        started = datetime(2026, 1, 1, tzinfo=timezone.utc)
        attempt = ExecutionAttempt(
            game=GameKey.BETTERGI, attempt_number=1,
            status=ExecutionStatus.RUNNING, started_at=started,
        )
        self.assertEqual(attempt.status, ExecutionStatus.RUNNING)

    def test_attempt_rejects_zero_attempt_number(self) -> None:
        with self.assertRaisesRegex(ValueError, "at least 1"):
            ExecutionAttempt(
                game=GameKey.MARCH7TH, attempt_number=0,
                status=ExecutionStatus.PENDING,
            )

    def test_attempt_rejects_finish_before_start(self) -> None:
        with self.assertRaisesRegex(ValueError, "earlier"):
            ExecutionAttempt(
                game=GameKey.BETTERGI, attempt_number=1,
                status=ExecutionStatus.SUCCESS,
                started_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
                finished_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            )


if __name__ == "__main__":
    unittest.main()
