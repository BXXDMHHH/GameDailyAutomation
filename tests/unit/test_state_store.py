from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path

from game_daily_automation.domain.enums import ExecutionStatus
from game_daily_automation.exceptions import StatePersistenceError
from game_daily_automation.infrastructure.state_store import SQLiteStateStore


class SQLiteStateStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database = Path(self.temp_dir.name) / "state.sqlite3"
        self.store = SQLiteStateStore(self.database)
        self.store.initialize()
        self.day = date(2026, 11, 26)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_schema_initialization_is_idempotent(self) -> None:
        self.store.initialize()
        self.store.ensure_daily_task(self.day)
        self.assertEqual(self.store.get_daily_task(self.day)["status"], "pending")

    def test_success_is_persisted_and_duplicate_start_blocked(self) -> None:
        self.store.start_attempt(self.day, "bettergi")
        self.store.finish_attempt(self.day, "bettergi", ExecutionStatus.SUCCESS)
        state = self.store.get_game_state(self.day, "bettergi")
        self.assertEqual(state.status, ExecutionStatus.SUCCESS)
        self.assertEqual(state.attempt_count, 1)
        self.assertEqual(self.store.get_daily_task(self.day)["status"], "running")
        with self.assertRaisesRegex(StatePersistenceError, "already succeeded"):
            self.store.start_attempt(self.day, "bettergi")

    def test_daily_success_requires_both_games(self) -> None:
        self.store.start_attempt(self.day, "bettergi")
        self.store.finish_attempt(self.day, "bettergi", ExecutionStatus.SUCCESS)
        with self.assertRaisesRegex(StatePersistenceError, "march7th"):
            self.store.complete_daily_task(self.day)
        self.store.start_attempt(self.day, "march7th")
        self.store.finish_attempt(self.day, "march7th", ExecutionStatus.SUCCESS)
        self.store.complete_daily_task(self.day)
        self.assertEqual(self.store.get_daily_task(self.day)["status"], "success")

    def test_two_games_have_independent_state(self) -> None:
        self.store.start_attempt(self.day, "bettergi")
        self.store.finish_attempt(self.day, "bettergi", ExecutionStatus.SUCCESS)
        self.store.start_attempt(self.day, "march7th")
        self.assertEqual(
            self.store.get_game_state(self.day, "bettergi").status,
            ExecutionStatus.SUCCESS,
        )
        self.assertEqual(
            self.store.get_game_state(self.day, "march7th").status,
            ExecutionStatus.RUNNING,
        )

    def test_retry_requires_confirmed_failure_and_explicit_permission(self) -> None:
        self.store.start_attempt(self.day, "bettergi")
        self.store.finish_attempt(self.day, "bettergi", ExecutionStatus.FAILED, error_message="confirmed")
        with self.assertRaises(StatePersistenceError):
            self.store.start_attempt(self.day, "bettergi")
        self.assertEqual(self.store.start_attempt(self.day, "bettergi", safe_to_retry=True), 2)
        self.store.finish_attempt(self.day, "bettergi", ExecutionStatus.FAILED)
        with self.assertRaisesRegex(StatePersistenceError, "attempt limit"):
            self.store.start_attempt(self.day, "bettergi", safe_to_retry=True)

    def test_unknown_is_not_retryable(self) -> None:
        self.store.start_attempt(self.day, "march7th")
        self.store.finish_attempt(self.day, "march7th", ExecutionStatus.UNKNOWN)
        with self.assertRaisesRegex(StatePersistenceError, "inspect evidence"):
            self.store.start_attempt(self.day, "march7th", safe_to_retry=True)

    def test_restart_recovery_converts_running_to_unknown(self) -> None:
        self.store.start_attempt(self.day, "bettergi")
        recovered = SQLiteStateStore(self.database)
        recovered.initialize()
        self.assertEqual(recovered.recover_interrupted(), 1)
        state = recovered.get_game_state(self.day, "bettergi")
        self.assertEqual(state.status, ExecutionStatus.UNKNOWN)
        self.assertIn("restart", state.error_message)
        with self.assertRaises(StatePersistenceError):
            recovered.start_attempt(self.day, "bettergi", safe_to_retry=True)

    def test_failed_database_open_does_not_claim_success(self) -> None:
        blocker = Path(self.temp_dir.name) / "blocker"
        blocker.write_text("not a directory", encoding="utf-8")
        broken = SQLiteStateStore(blocker / "state.db")
        with self.assertRaises(StatePersistenceError):
            broken.initialize()

    def test_date_and_game_validation(self) -> None:
        with self.assertRaises(ValueError):
            self.store.get_game_state(self.day, "unknown-game")
        with self.assertRaises(ValueError):
            self.store.get_daily_task("not-a-date")


if __name__ == "__main__":
    unittest.main()
