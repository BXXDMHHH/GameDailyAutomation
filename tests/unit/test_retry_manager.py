from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path

from game_daily_automation.core.retry_manager import RetryManager
from game_daily_automation.domain.enums import AdapterExecutionStatus, ExecutionStatus, GameKey
from game_daily_automation.domain.models import AdapterExecutionResult
from game_daily_automation.infrastructure.state_store import SQLiteStateStore


class FakeAdapter:
    def __init__(self):
        self.calls = 0

    def execute_daily(self):
        self.calls += 1
        return AdapterExecutionResult(GameKey.BETTERGI, AdapterExecutionStatus.SUCCESS)


class RetrySessionGuardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = SQLiteStateStore(Path(self.temp.name) / "state.db")
        self.store.initialize()
        self.day = date(2026, 11, 26)

    def tearDown(self):
        self.temp.cleanup()

    def test_locked_before_first_attempt_does_not_persist_running_or_execute(self):
        adapter = FakeAdapter()
        manager = RetryManager(self.store, is_session_unlocked=lambda: False)
        result = manager.run_game(self.day, "bettergi", adapter)
        self.assertEqual(result.status, ExecutionStatus.INTERRUPTED)
        self.assertEqual(adapter.calls, 0)
        self.assertEqual(self.store.list_game_attempts(self.day), [])

    def test_lock_between_attempts_prevents_retry(self):
        adapter = FakeAdapter()
        states = iter([True, False])
        from game_daily_automation.domain.models import AdapterExecutionResult
        from game_daily_automation.domain.enums import AdapterExecutionStatus
        class FailsOnce:
            def __init__(self): self.calls = 0
            def execute_daily(self):
                self.calls += 1
                return AdapterExecutionResult(GameKey.BETTERGI, AdapterExecutionStatus.FAILED)
        failing = FailsOnce()
        manager = RetryManager(
            self.store, retry_delay_seconds=0, is_safe_to_retry=lambda _: True,
            is_session_unlocked=lambda: next(states),
        )
        result = manager.run_game(self.day, "bettergi", failing)
        self.assertEqual(result.status, ExecutionStatus.INTERRUPTED)
        self.assertEqual(failing.calls, 1)
        self.assertEqual(len(self.store.list_game_attempts(self.day)), 1)


if __name__ == "__main__":
    unittest.main()
