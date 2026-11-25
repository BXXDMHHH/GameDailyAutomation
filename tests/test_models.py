from __future__ import annotations

import unittest
from datetime import datetime, timezone

from gamedaily.models import ExecutionAttempt, ExecutionStatus, Game


class ModelTests(unittest.TestCase):
    def test_attempt_accepts_valid_state(self) -> None:
        started = datetime(2026, 1, 1, tzinfo=timezone.utc)
        attempt = ExecutionAttempt(
            game=Game.GENSHIN_IMPACT, attempt_number=1,
            status=ExecutionStatus.RUNNING, started_at=started,
        )
        self.assertEqual(attempt.status, ExecutionStatus.RUNNING)

    def test_attempt_rejects_zero_attempt_number(self) -> None:
        with self.assertRaisesRegex(ValueError, "at least 1"):
            ExecutionAttempt(
                game=Game.HONKAI_STAR_RAIL, attempt_number=0,
                status=ExecutionStatus.PENDING,
            )

    def test_attempt_rejects_finish_before_start(self) -> None:
        with self.assertRaisesRegex(ValueError, "earlier"):
            ExecutionAttempt(
                game=Game.GENSHIN_IMPACT, attempt_number=1,
                status=ExecutionStatus.SUCCESS,
                started_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
                finished_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            )


if __name__ == "__main__":
    unittest.main()
