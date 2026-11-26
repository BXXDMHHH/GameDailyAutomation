from __future__ import annotations

import subprocess
import unittest
from unittest.mock import MagicMock, patch

from game_daily_automation.infrastructure.process_runner import ProcessRunner


class ProcessRunnerTests(unittest.TestCase):
    @patch("game_daily_automation.infrastructure.process_runner.subprocess.Popen")
    def test_uses_argument_list_shell_false_and_captures_both_streams(self, popen) -> None:
        process = MagicMock()
        process.pid = 123
        process.returncode = 0
        process.communicate.return_value = ("all good", "warning")
        process.poll.return_value = 0
        popen.return_value = process

        result = ProcessRunner().run("tool.exe", ["arg with spaces"])
        self.assertTrue(result.started)
        self.assertEqual(result.command, ("tool.exe", "arg with spaces"))
        self.assertEqual(result.stdout, "all good")
        self.assertEqual(result.stderr, "warning")
        self.assertFalse(popen.call_args.kwargs["shell"])
        self.assertEqual(popen.call_args.args[0], ["tool.exe", "arg with spaces"])

    @patch("game_daily_automation.infrastructure.process_runner.subprocess.Popen")
    def test_missing_executable_is_start_failure(self, popen) -> None:
        popen.side_effect = FileNotFoundError("not found")
        result = ProcessRunner().run("missing.exe", [])
        self.assertFalse(result.started)
        self.assertIn("FileNotFoundError", result.start_error or "")

    @patch("game_daily_automation.infrastructure.process_runner.subprocess.Popen")
    @patch("game_daily_automation.infrastructure.process_runner.os.name", "posix")
    def test_timeout_terminates_process_and_returns_bounded_result(self, popen) -> None:
        process = MagicMock()
        process.pid = 123
        process.returncode = -9
        process.poll.side_effect = [None, None, -9]
        process.communicate.side_effect = [
            subprocess.TimeoutExpired(["tool"], 1, output=b"partial", stderr=b"err"),
            ("partial", "err"),
        ]
        popen.return_value = process
        # os.killpg does not exist on Windows. create=True lets this test
        # emulate the POSIX-only API while keeping the platform-independent
        # production code unchanged.
        with patch(
            "game_daily_automation.infrastructure.process_runner.os.killpg",
            create=True,
        ), patch(
            "game_daily_automation.infrastructure.process_runner.signal.SIGKILL",
            9,
            create=True,
        ):
            result = ProcessRunner(cleanup_timeout_seconds=0.01).run(
                "tool.exe", [], timeout_seconds=1
            )
        self.assertTrue(result.started)
        self.assertTrue(result.timed_out)
        self.assertEqual(result.stdout, "partial")
        self.assertEqual(result.stderr, "err")
        process.communicate.assert_any_call(timeout=1)

    @patch("game_daily_automation.infrastructure.process_runner.subprocess.Popen")
    def test_monitor_exception_does_not_wait_forever(self, popen) -> None:
        process = MagicMock()
        process.pid = 321
        process.poll.return_value = None
        process.communicate.side_effect = RuntimeError("pipe read failed")
        popen.return_value = process
        with patch.object(ProcessRunner, "_terminate_tree") as terminate:
            result = ProcessRunner().run("tool.exe", [])
        terminate.assert_called_once_with(process)
        self.assertIn("pipe read failed", result.execution_error or "")

    def test_rejects_non_positive_timeout(self) -> None:
        with self.assertRaises(ValueError):
            ProcessRunner().run("tool.exe", [], timeout_seconds=0)


if __name__ == "__main__":
    unittest.main()
