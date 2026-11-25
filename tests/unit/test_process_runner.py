from __future__ import annotations

import subprocess
import unittest
from unittest.mock import patch

from game_daily_automation.infrastructure.process_runner import ProcessRunner


class ProcessRunnerTests(unittest.TestCase):
    @patch("game_daily_automation.infrastructure.process_runner.subprocess.run")
    def test_uses_argument_list_and_shell_false(self, run_mock) -> None:
        run_mock.return_value = subprocess.CompletedProcess(
            args=["tool.exe", "arg with spaces"], returncode=0,
            stdout="ok", stderr="",
        )
        result = ProcessRunner().run("tool.exe", ["arg with spaces"])
        self.assertTrue(result.started)
        self.assertEqual(result.command, ("tool.exe", "arg with spaces"))
        self.assertFalse(run_mock.call_args.kwargs["shell"])

    @patch("game_daily_automation.infrastructure.process_runner.subprocess.run")
    def test_missing_executable_is_start_failure(self, run_mock) -> None:
        run_mock.side_effect = FileNotFoundError("not found")
        result = ProcessRunner().run("missing.exe", [])
        self.assertFalse(result.started)
        self.assertIn("FileNotFoundError", result.start_error or "")

    @patch("game_daily_automation.infrastructure.process_runner.subprocess.run")
    def test_timeout_is_recorded(self, run_mock) -> None:
        run_mock.side_effect = subprocess.TimeoutExpired(
            cmd=["tool.exe"], timeout=1, output=b"partial", stderr=b""
        )
        result = ProcessRunner().run("tool.exe", [], timeout_seconds=1)
        self.assertTrue(result.started)
        self.assertTrue(result.timed_out)
        self.assertEqual(result.stdout, "partial")


if __name__ == "__main__":
    unittest.main()
