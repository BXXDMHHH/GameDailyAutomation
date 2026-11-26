from __future__ import annotations

import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from game_daily_automation.core.orchestrator import DailyOrchestrator
from game_daily_automation.core.retry_manager import RetryManager
from game_daily_automation.domain.enums import AdapterExecutionStatus, ExecutionStatus, GameKey
from game_daily_automation.exceptions import StatePersistenceError
from game_daily_automation.domain.models import AdapterExecutionResult
from game_daily_automation.infrastructure.state_store import SQLiteStateStore


class FakeAdapter:
    def __init__(self, name, results, events):
        self.name, self.results, self.events = name, list(results), events

    def execute_daily(self):
        self.events.append(("start", self.name))
        result = self.results.pop(0)
        self.events.append(("finish", self.name))
        return AdapterExecutionResult(game=GameKey.BETTERGI if self.name == "bettergi" else GameKey.MARCH7TH, status=result, detail=result.value)


class OrchestratorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = SQLiteStateStore(Path(self.temp.name) / "state.db")
        self.store.initialize()
        self.events = []

    def tearDown(self):
        self.temp.cleanup()

    def adapter(self, name, *statuses):
        return FakeAdapter(name, statuses, self.events)

    def orchestrator(self, bg, m7, **kwargs):
        retry = RetryManager(
            self.store, retry_delay_seconds=0, sleep=lambda _: None,
            is_safe_to_retry=kwargs.pop("is_safe_to_retry", lambda result: True),
        )
        return DailyOrchestrator(self.store, bg, m7, retry_manager=retry, **kwargs)

    def test_bettergi_precedes_march7th_and_workflow_completes(self):
        day = datetime(2026, 11, 26, 17, 1)
        result = self.orchestrator(
            self.adapter("bettergi", AdapterExecutionStatus.SUCCESS),
            self.adapter("march7th", AdapterExecutionStatus.SUCCESS),
        ).run_if_due(now=day)
        self.assertEqual(result.status, ExecutionStatus.SUCCESS)
        self.assertEqual([event[1] for event in self.events if event[0] == "start"], ["bettergi", "march7th"])
        self.assertEqual(self.store.get_daily_task(day.date())["status"], "success")

    def test_not_due_and_locked_session_do_not_start_adapters(self):
        orchestrator = self.orchestrator(
            self.adapter("bettergi", AdapterExecutionStatus.SUCCESS),
            self.adapter("march7th", AdapterExecutionStatus.SUCCESS),
            is_session_unlocked=lambda: False,
        )
        self.assertEqual(orchestrator.run_if_due(now=datetime(2026, 11, 26, 16, 59)).status, ExecutionStatus.PENDING)
        self.assertEqual(orchestrator.run_if_due(now=datetime(2026, 11, 26, 17, 1)).status, ExecutionStatus.PENDING)
        self.assertEqual(self.events, [])

    def test_lock_after_bettergi_prevents_march7th_start(self):
        day = datetime(2026, 11, 26, 18, 0)
        session_checks = iter([True, False])
        retry = RetryManager(
            self.store, retry_delay_seconds=0, sleep=lambda _: None,
            is_session_unlocked=lambda: next(session_checks),
        )
        orchestrator = DailyOrchestrator(
            self.store,
            self.adapter("bettergi", AdapterExecutionStatus.SUCCESS),
            self.adapter("march7th", AdapterExecutionStatus.SUCCESS),
            retry_manager=retry,
            is_session_unlocked=lambda: True,
        )
        result = orchestrator.run_if_due(now=day)
        self.assertEqual(result.status, ExecutionStatus.INTERRUPTED)
        self.assertEqual([event[1] for event in self.events if event[0] == "start"], ["bettergi"])

    def test_one_game_failure_does_not_block_other_game(self):
        result = self.orchestrator(
            self.adapter("bettergi", AdapterExecutionStatus.FAILED, AdapterExecutionStatus.FAILED),
            self.adapter("march7th", AdapterExecutionStatus.SUCCESS),
        ).run_if_due(now=datetime(2026, 11, 26, 18, 0))
        self.assertEqual(result.status, ExecutionStatus.FAILED)
        self.assertEqual([event[1] for event in self.events if event[0] == "start"],
                         ["bettergi", "bettergi", "march7th"])

    def test_retry_is_bounded_to_two_attempts(self):
        self.orchestrator(
            self.adapter("bettergi", *([AdapterExecutionStatus.FAILED] * 3)),
            self.adapter("march7th", AdapterExecutionStatus.SUCCESS),
        ).run_if_due(now=datetime(2026, 11, 26, 18, 0))
        self.assertEqual(sum(1 for event in self.events if event == ("start", "bettergi")), 2)

    def test_unknown_is_not_retried_but_other_game_runs(self):
        result = self.orchestrator(
            self.adapter("bettergi", AdapterExecutionStatus.UNKNOWN),
            self.adapter("march7th", AdapterExecutionStatus.SUCCESS),
        ).run_if_due(now=datetime(2026, 11, 26, 18, 0))
        self.assertEqual(result.status, ExecutionStatus.UNKNOWN)
        self.assertEqual([event[1] for event in self.events if event[0] == "start"], ["bettergi", "march7th"])

    def test_unsafe_failure_is_not_retried(self):
        self.orchestrator(
            self.adapter("bettergi", AdapterExecutionStatus.FAILED, AdapterExecutionStatus.SUCCESS),
            self.adapter("march7th", AdapterExecutionStatus.SUCCESS),
            is_safe_to_retry=lambda _: False,
        ).run_if_due(now=datetime(2026, 11, 26, 18, 0))
        self.assertEqual(sum(1 for event in self.events if event == ("start", "bettergi")), 1)

    def test_human_review_can_resolve_unknown_and_approve_one_safe_retry(self):
        day = datetime(2026, 11, 26, 18, 0)
        self.store.start_attempt(day.date(), "bettergi")
        self.store.finish_attempt(day.date(), "bettergi", ExecutionStatus.UNKNOWN, error_message="ambiguous")
        self.store.resolve_unknown(
            day.date(), "bettergi", confirmed_status=ExecutionStatus.FAILED,
            evidence_note="Checked tool log: task did not complete.",
            safe_to_retry=True,
        )
        result = self.orchestrator(
            self.adapter("bettergi", AdapterExecutionStatus.SUCCESS),
            self.adapter("march7th", AdapterExecutionStatus.SUCCESS),
        ).run_if_due(now=day)
        self.assertEqual(result.games[0].status, ExecutionStatus.SUCCESS)
        self.assertEqual(result.games[0].attempts, 2)

    def test_human_review_requires_evidence_and_unknown_state(self):
        day = datetime(2026, 11, 26)
        with self.assertRaises(ValueError):
            self.store.resolve_unknown(day, "bettergi", confirmed_status=ExecutionStatus.FAILED, evidence_note=" ")
        with self.assertRaises(StatePersistenceError):
            self.store.resolve_unknown(day, "bettergi", confirmed_status=ExecutionStatus.FAILED, evidence_note="reviewed")

    def test_state_persistence_failure_prevents_external_execution(self):
        from unittest.mock import patch

        orchestrator = self.orchestrator(
            self.adapter("bettergi", AdapterExecutionStatus.SUCCESS),
            self.adapter("march7th", AdapterExecutionStatus.SUCCESS),
        )
        with patch.object(self.store, "start_attempt", side_effect=StatePersistenceError("disk unavailable")):
            with self.assertRaises(StatePersistenceError):
                orchestrator.run_if_due(now=datetime(2026, 11, 26, 18, 0))
        self.assertEqual(self.events, [])

    def test_adapter_exception_is_recorded_unknown_and_next_game_runs(self):
        class RaisingAdapter:
            def execute_daily(self):
                raise RuntimeError("simulated adapter error")

        result = self.orchestrator(
            RaisingAdapter(),
            self.adapter("march7th", AdapterExecutionStatus.SUCCESS),
        ).run_if_due(now=datetime(2026, 11, 26, 18, 0))
        self.assertEqual(result.status, ExecutionStatus.UNKNOWN)
        self.assertEqual([event[1] for event in self.events if event[0] == "start"], ["march7th"])
        self.assertEqual(self.store.get_game_state(datetime(2026, 11, 26).date(), "bettergi").status,
                         ExecutionStatus.UNKNOWN)

    def test_successful_task_is_not_repeated_after_restart(self):
        bg = self.adapter("bettergi", AdapterExecutionStatus.SUCCESS)
        m7 = self.adapter("march7th", AdapterExecutionStatus.SUCCESS)
        orchestrator = self.orchestrator(bg, m7)
        now = datetime(2026, 11, 26, 18, 0)
        orchestrator.run_if_due(now=now)
        before = len(self.events)
        again = self.orchestrator(self.adapter("bettergi"), self.adapter("march7th")).run_if_due(now=now)
        self.assertEqual(again.status, ExecutionStatus.SUCCESS)
        self.assertEqual(len(self.events), before)


if __name__ == "__main__":
    unittest.main()
