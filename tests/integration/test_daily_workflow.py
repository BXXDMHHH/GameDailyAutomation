from __future__ import annotations

import json
import logging
import tempfile
import sys
import unittest
from unittest.mock import patch
from datetime import date, datetime, timedelta
from pathlib import Path

from game_daily_automation.adapters import BetterGIAdapter, March7thAdapter
from game_daily_automation.config.loader import GameToolConfig
from game_daily_automation.core.orchestrator import DailyOrchestrator
from game_daily_automation.core.retry_manager import RetryManager
from game_daily_automation.domain.enums import (
    AdapterExecutionStatus, ExecutionStatus, GameKey,
)
from game_daily_automation.domain.models import AdapterExecutionResult, ProcessResult
from game_daily_automation.exceptions import StatePersistenceError
from game_daily_automation.infrastructure.logging_config import LOGGER_NAME
from game_daily_automation.infrastructure.process_runner import ProcessRunner
from game_daily_automation.infrastructure.state_store import SQLiteStateStore
from game_daily_automation.main import main


class ScriptedAdapter:
    def __init__(self, game: GameKey, *results: AdapterExecutionStatus):
        self.game = game
        self.results = list(results)
        self.calls = 0

    def execute_daily(self):
        self.calls += 1
        if not self.results:
            raise AssertionError(f"Unexpected extra execution for {self.game}")
        return AdapterExecutionResult(self.game, self.results.pop(0))


class FixedProcessRunner:
    def __init__(self, result: ProcessResult):
        self.result = result
        self.calls = 0

    def run(self, executable, arguments, **kwargs):
        self.calls += 1
        return self.result


class DailyWorkflowIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.database = self.root / "state.sqlite3"
        self.store = SQLiteStateStore(self.database)
        self.store.initialize()
        self.day = date(2026, 11, 26)

    def tearDown(self):
        self.temp.cleanup()

    def make_orchestrator(
        self, bettergi, march7th, *, unlocked=lambda: True,
        safe_retry=lambda _result: True, retry_delay=0,
    ):
        retry = RetryManager(
            self.store, retry_delay_seconds=retry_delay, sleep=lambda _: None,
            is_safe_to_retry=safe_retry, is_session_unlocked=unlocked,
        )
        return DailyOrchestrator(
            self.store, bettergi, march7th, retry_manager=retry,
            is_session_unlocked=lambda: True,
        )

    def run_day(self, orchestrator, day=None, hour=18):
        day = day or self.day
        return orchestrator.run_if_due(now=datetime(day.year, day.month, day.day, hour, 0))

    def test_both_games_succeed_in_required_order(self):
        bg = ScriptedAdapter(GameKey.BETTERGI, AdapterExecutionStatus.SUCCESS)
        m7 = ScriptedAdapter(GameKey.MARCH7TH, AdapterExecutionStatus.SUCCESS)
        result = self.run_day(self.make_orchestrator(bg, m7))
        self.assertEqual(result.status, ExecutionStatus.SUCCESS)
        self.assertEqual((bg.calls, m7.calls), (1, 1))
        self.assertEqual(self.store.get_daily_task(self.day)["status"], "success")

    def test_bettergi_failure_then_safe_retry_succeeds(self):
        bg = ScriptedAdapter(
            GameKey.BETTERGI, AdapterExecutionStatus.FAILED, AdapterExecutionStatus.SUCCESS
        )
        m7 = ScriptedAdapter(GameKey.MARCH7TH, AdapterExecutionStatus.SUCCESS)
        result = self.run_day(self.make_orchestrator(bg, m7))
        self.assertEqual(result.status, ExecutionStatus.SUCCESS)
        self.assertEqual(bg.calls, 2)
        self.assertEqual(self.store.get_game_state(self.day, "bettergi").attempt_count, 2)

    def test_march7th_failure_then_safe_retry_succeeds(self):
        bg = ScriptedAdapter(GameKey.BETTERGI, AdapterExecutionStatus.SUCCESS)
        m7 = ScriptedAdapter(
            GameKey.MARCH7TH, AdapterExecutionStatus.FAILED, AdapterExecutionStatus.SUCCESS
        )
        result = self.run_day(self.make_orchestrator(bg, m7))
        self.assertEqual(result.status, ExecutionStatus.SUCCESS)
        self.assertEqual(bg.calls, 1)
        self.assertEqual(m7.calls, 2)

    def test_one_game_final_failure_does_not_skip_other_game(self):
        bg = ScriptedAdapter(
            GameKey.BETTERGI, AdapterExecutionStatus.FAILED, AdapterExecutionStatus.FAILED
        )
        m7 = ScriptedAdapter(GameKey.MARCH7TH, AdapterExecutionStatus.SUCCESS)
        result = self.run_day(self.make_orchestrator(bg, m7))
        self.assertEqual(result.status, ExecutionStatus.FAILED)
        self.assertEqual((bg.calls, m7.calls), (2, 1))

    def test_both_games_finally_fail_with_two_attempts_each(self):
        bg = ScriptedAdapter(
            GameKey.BETTERGI, AdapterExecutionStatus.FAILED, AdapterExecutionStatus.FAILED
        )
        m7 = ScriptedAdapter(
            GameKey.MARCH7TH, AdapterExecutionStatus.FAILED, AdapterExecutionStatus.FAILED
        )
        result = self.run_day(self.make_orchestrator(bg, m7))
        self.assertEqual(result.status, ExecutionStatus.FAILED)
        self.assertEqual((bg.calls, m7.calls), (2, 2))
        self.assertEqual(len(self.store.list_game_attempts(self.day)), 4)

    def _adapter_from_process_result(self, game, result):
        executable = self.root / f"{game.value}.exe"
        executable.write_bytes(b"test executable placeholder")
        config = GameToolConfig(
            executable=str(executable), arguments=("verified-test-argument",)
        )
        runner = FixedProcessRunner(result)
        adapter_type = BetterGIAdapter if game == GameKey.BETTERGI else March7thAdapter
        return adapter_type(config, process_runner=runner), runner

    def test_process_start_failure_is_recorded_and_other_game_runs(self):
        bg, runner = self._adapter_from_process_result(
            GameKey.BETTERGI,
            ProcessResult(
                started=False, command=("bettergi.exe",), return_code=None,
                start_error="FileNotFoundError: simulated",
            ),
        )
        m7 = ScriptedAdapter(GameKey.MARCH7TH, AdapterExecutionStatus.SUCCESS)
        result = self.run_day(self.make_orchestrator(bg, m7, safe_retry=lambda _: False))
        self.assertEqual(result.status, ExecutionStatus.FAILED)
        self.assertEqual(runner.calls, 1)
        self.assertEqual(m7.calls, 1)
        self.assertEqual(self.store.get_game_state(self.day, "bettergi").status, ExecutionStatus.FAILED)

    def test_process_timeout_becomes_unknown_and_is_not_retried(self):
        bg, runner = self._adapter_from_process_result(
            GameKey.BETTERGI,
            ProcessResult(
                started=True, command=("bettergi.exe",), return_code=-9,
                timed_out=True, pid=4321,
            ),
        )
        m7 = ScriptedAdapter(GameKey.MARCH7TH, AdapterExecutionStatus.SUCCESS)
        result = self.run_day(self.make_orchestrator(bg, m7))
        self.assertEqual(result.status, ExecutionStatus.UNKNOWN)
        self.assertEqual(runner.calls, 1)
        self.assertEqual(m7.calls, 1)
        self.assertEqual(self.store.get_game_state(self.day, "bettergi").status, ExecutionStatus.UNKNOWN)

    def test_real_process_start_failure_is_detected(self):
        missing = self.root / "definitely-not-installed-tool.exe"
        result = ProcessRunner(cleanup_timeout_seconds=1).run(
            missing, [], timeout_seconds=2
        )
        self.assertFalse(result.started)
        self.assertIn("FileNotFoundError", result.start_error or "")

    def test_real_python_child_timeout_is_terminated(self):
        runner = ProcessRunner(cleanup_timeout_seconds=1)
        result = runner.run(
            sys.executable,
            ["-c", "import time; time.sleep(10)"],
            timeout_seconds=0.25,
        )
        self.assertTrue(result.started)
        self.assertTrue(result.timed_out)
        self.assertLess(result.duration_seconds, 6.0)

    def test_unknown_result_is_not_retried(self):
        bg = ScriptedAdapter(GameKey.BETTERGI, AdapterExecutionStatus.UNKNOWN)
        m7 = ScriptedAdapter(GameKey.MARCH7TH, AdapterExecutionStatus.SUCCESS)
        result = self.run_day(self.make_orchestrator(bg, m7))
        self.assertEqual(result.status, ExecutionStatus.UNKNOWN)
        self.assertEqual(bg.calls, 1)
        self.assertEqual(m7.calls, 1)

    def test_lock_during_first_game_prevents_next_game_until_unlock(self):
        checks = iter([True, False])
        bg = ScriptedAdapter(GameKey.BETTERGI, AdapterExecutionStatus.SUCCESS)
        m7 = ScriptedAdapter(GameKey.MARCH7TH, AdapterExecutionStatus.SUCCESS)
        first = self.make_orchestrator(bg, m7, unlocked=lambda: next(checks))
        interrupted = self.run_day(first)
        self.assertEqual(interrupted.status, ExecutionStatus.INTERRUPTED)
        self.assertEqual((bg.calls, m7.calls), (1, 0))

        resumed = self.run_day(self.make_orchestrator(bg, m7))
        self.assertEqual(resumed.status, ExecutionStatus.SUCCESS)
        self.assertEqual((bg.calls, m7.calls), (1, 1))

    def test_crash_restart_requires_evidence_review_before_resume(self):
        self.store.start_attempt(self.day, "bettergi")
        restarted_store = SQLiteStateStore(self.database)
        restarted_store.initialize()
        self.assertEqual(restarted_store.recover_interrupted(), 1)
        self.assertTrue(restarted_store.has_unresolved_recovery())

        with self.assertRaises(StatePersistenceError):
            restarted_store.start_attempt(self.day, "bettergi", safe_to_retry=True)

        restarted_store.resolve_unknown(
            self.day, "bettergi", confirmed_status=ExecutionStatus.FAILED,
            evidence_note="Integration test verified process had stopped without completing.",
            safe_to_retry=True,
        )
        self.assertFalse(restarted_store.has_unresolved_recovery())
        self.store = restarted_store
        bg = ScriptedAdapter(GameKey.BETTERGI, AdapterExecutionStatus.SUCCESS)
        m7 = ScriptedAdapter(GameKey.MARCH7TH, AdapterExecutionStatus.SUCCESS)
        result = self.run_day(self.make_orchestrator(bg, m7))
        self.assertEqual(result.status, ExecutionStatus.SUCCESS)
        self.assertEqual(self.store.get_game_state(self.day, "bettergi").attempt_count, 2)

    def test_cross_midnight_and_date_switch_use_separate_daily_records(self):
        bg = ScriptedAdapter(
            GameKey.BETTERGI,
            AdapterExecutionStatus.SUCCESS, AdapterExecutionStatus.SUCCESS,
        )
        m7 = ScriptedAdapter(
            GameKey.MARCH7TH,
            AdapterExecutionStatus.SUCCESS, AdapterExecutionStatus.SUCCESS,
        )
        orchestrator = self.make_orchestrator(bg, m7)
        first = orchestrator.run_if_due(now=datetime(2026, 11, 26, 23, 59))
        before_next_schedule = orchestrator.run_if_due(now=datetime(2026, 11, 27, 0, 1))
        self.assertEqual(first.status, ExecutionStatus.SUCCESS)
        self.assertEqual(before_next_schedule.status, ExecutionStatus.PENDING)
        self.assertIsNone(self.store.get_daily_task(date(2026, 11, 27)))

        next_day = orchestrator.run_if_due(now=datetime(2026, 11, 27, 17, 1))
        self.assertEqual(next_day.status, ExecutionStatus.SUCCESS)
        self.assertEqual(self.store.get_daily_task(date(2026, 11, 26))["status"], "success")
        self.assertEqual(self.store.get_daily_task(date(2026, 11, 27))["status"], "success")
        self.assertEqual((bg.calls, m7.calls), (2, 2))

    def test_corrupt_database_fails_closed_without_adapter_execution(self):
        corrupt = self.root / "corrupt.sqlite3"
        corrupt.write_bytes(b"not a sqlite database")
        broken_store = SQLiteStateStore(corrupt)
        with self.assertRaises(StatePersistenceError):
            broken_store.initialize()
        bg = ScriptedAdapter(GameKey.BETTERGI, AdapterExecutionStatus.SUCCESS)
        m7 = ScriptedAdapter(GameKey.MARCH7TH, AdapterExecutionStatus.SUCCESS)
        self.assertEqual((bg.calls, m7.calls), (0, 0))

    def test_corrupt_database_blocks_main_before_adapter_construction(self):
        corrupt = self.root / "corrupt-main.sqlite3"
        corrupt.write_bytes(b"not a sqlite database")
        config = self.root / "settings.json"
        config.write_text(json.dumps({
            "storage": {
                "database_path": str(corrupt),
                "log_directory": str(self.root / "logs"),
            }
        }), encoding="utf-8")
        try:
            with patch("game_daily_automation.main.sys.platform", "win32"):
                with patch("game_daily_automation.main.BetterGIAdapter") as bettergi:
                    with patch("game_daily_automation.main.March7thAdapter") as march7th:
                        result = main(["--config", str(config)])
            self.assertEqual(result, 1)
            bettergi.assert_not_called()
            march7th.assert_not_called()
        finally:
            logger = logging.getLogger(LOGGER_NAME)
            for handler in logger.handlers[:]:
                logger.removeHandler(handler)
                handler.close()

    def test_seven_consecutive_days_complete_once_per_date(self):
        bg = ScriptedAdapter(GameKey.BETTERGI, *([AdapterExecutionStatus.SUCCESS] * 7))
        m7 = ScriptedAdapter(GameKey.MARCH7TH, *([AdapterExecutionStatus.SUCCESS] * 7))
        orchestrator = self.make_orchestrator(bg, m7)
        for offset in range(7):
            day = self.day + timedelta(days=offset)
            result = self.run_day(orchestrator, day)
            self.assertEqual(result.status, ExecutionStatus.SUCCESS, day.isoformat())
            duplicate = self.run_day(orchestrator, day)
            self.assertEqual(duplicate.status, ExecutionStatus.SUCCESS)
        self.assertEqual((bg.calls, m7.calls), (7, 7))
        for offset in range(7):
            self.assertEqual(
                self.store.get_daily_task(self.day + timedelta(days=offset))["status"],
                "success",
            )


if __name__ == "__main__":
    unittest.main()
