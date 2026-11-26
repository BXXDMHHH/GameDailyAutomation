from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from game_daily_automation.adapters import BetterGIAdapter, March7thAdapter
from game_daily_automation.config.loader import GameToolConfig
from game_daily_automation.domain.enums import AdapterExecutionStatus, GameKey
from game_daily_automation.domain.models import ProcessResult


class FakeProcessRunner:
    def __init__(self, result: ProcessResult | None = None) -> None:
        self.result = result or ProcessResult(
            started=True, command=("tool.exe",), return_code=0
        )
        self.calls: list[tuple[str, tuple[str, ...]]] = []

    def run(self, executable, arguments, **kwargs) -> ProcessResult:
        self.calls.append((str(executable), tuple(arguments)))
        return self.result


class AdapterTests(unittest.TestCase):
    def test_adapters_initialize_independently(self) -> None:
        bettergi = BetterGIAdapter(GameToolConfig(executable="missing-bettergi.exe"))
        march7th = March7thAdapter(GameToolConfig())
        self.assertEqual(bettergi.game_key, GameKey.BETTERGI)
        self.assertEqual(march7th.game_key, GameKey.MARCH7TH)
        self.assertFalse(bettergi.check_available().available)
        self.assertFalse(march7th.check_available().available)

    def test_empty_arguments_do_not_guess_a_cli_command(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            executable = Path(temp_dir) / "tool.exe"
            executable.touch()
            adapter = BetterGIAdapter(GameToolConfig(executable=str(executable)))
            result = adapter.execute_daily()
            self.assertEqual(result.status, AdapterExecutionStatus.NOT_CONFIGURED)
            self.assertIn("arguments are empty", result.detail or "")

    def test_process_exit_zero_is_unknown_without_verified_classifier(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            executable = Path(temp_dir) / "tool.exe"
            executable.touch()
            runner = FakeProcessRunner(ProcessResult(
                started=True, command=("tool.exe", "verified-arg"), return_code=0
            ))
            adapter = BetterGIAdapter(
                GameToolConfig(executable=str(executable), arguments=("verified-arg",)),
                process_runner=runner,
            )
            result = adapter.execute_daily()
            self.assertEqual(result.status, AdapterExecutionStatus.UNKNOWN)
            self.assertEqual(runner.calls[0][1], ("verified-arg",))

    def test_verified_classifier_can_report_success_or_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            executable = Path(temp_dir) / "m7a.exe"
            executable.touch()
            config = GameToolConfig(
                executable=str(executable), arguments=("verified-task-id",)
            )
            success = March7thAdapter(
                config, process_runner=FakeProcessRunner(),
                result_classifier=lambda _: AdapterExecutionStatus.SUCCESS,
            )
            failure = March7thAdapter(
                config, process_runner=FakeProcessRunner(),
                result_classifier=lambda _: AdapterExecutionStatus.FAILED,
            )
            self.assertEqual(success.execute_daily().status, AdapterExecutionStatus.SUCCESS)
            self.assertEqual(failure.execute_daily().status, AdapterExecutionStatus.FAILED)

    def test_start_failure_is_distinct_from_task_failure(self) -> None:
        adapter = BetterGIAdapter(GameToolConfig())
        result = adapter.identify_result(ProcessResult(
            started=False, command=("missing.exe",), return_code=None,
            start_error="FileNotFoundError",
        ))
        self.assertEqual(result.status, AdapterExecutionStatus.START_FAILED)

    def test_timeout_has_distinct_process_status(self) -> None:
        adapter = March7thAdapter(GameToolConfig())
        result = adapter.identify_result(ProcessResult(
            started=True, command=("m7a.exe",), return_code=None, timed_out=True
        ))
        self.assertEqual(result.status, AdapterExecutionStatus.TIMEOUT)

    def test_version_probe_runs_only_when_explicitly_configured(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            executable = Path(temp_dir) / "tool.exe"
            executable.touch()
            runner = FakeProcessRunner(ProcessResult(
                started=True, command=("tool.exe", "--version"), return_code=0,
                stdout="Version 1.2.3",
            ))
            adapter = BetterGIAdapter(
                GameToolConfig(
                    executable=str(executable), version_arguments=("--version",)
                ),
                process_runner=runner,
            )
            report = adapter.check_available()
            self.assertTrue(report.available)
            self.assertEqual(report.version_output, "Version 1.2.3")
            self.assertEqual(runner.calls[0][1], ("--version",))


if __name__ == "__main__":
    unittest.main()
