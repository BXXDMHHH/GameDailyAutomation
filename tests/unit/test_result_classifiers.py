from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from game_daily_automation.adapters import BetterGIAdapter, March7thAdapter
from game_daily_automation.adapters.result_classifiers import BetterGIResultClassifier, March7thResultClassifier
from game_daily_automation.config.loader import GameToolConfig
from game_daily_automation.domain.enums import AdapterExecutionStatus
from game_daily_automation.domain.models import ProcessResult


def process_result(*, code=0, stdout="", stderr="", timed_out=False):
    return ProcessResult(started=True, command=("tool.exe",), return_code=code,
                         stdout=stdout, stderr=stderr, timed_out=timed_out, pid=1234)


def m7_record(**overrides):
    record = {
        "schema": 1, "run_id": "20261126-173416-e5be", "status": "success",
        "task": "daily",
        "args": ["daily", "--after-finish", "None", "--json", "--non-interactive"],
        "version": "v2026.11.8", "pid": 10580,
        "started_at": "2026-11-26T17:34:16+08:00",
        "ended_at": "2026-11-26T17:35:27+08:00",
        "exit_code": 0, "reason": None, "error": None, "lock": "acquired",
    }
    record.update(overrides)
    return record


class FakeRunner:
    def __init__(self, result, callback=None):
        self.result, self.callback = result, callback

    def run(self, executable, arguments, **kwargs):
        if self.callback:
            self.callback()
        return self.result


class BetterGIClassifierTests(unittest.TestCase):
    def test_only_new_invocation_log_lines_can_prove_success(self):
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "bettergi.log"
            log.write_text("old session 一条龙和配置组任务结束\n", encoding="utf-8")
            classifier = BetterGIResultClassifier(log)
            snapshot = classifier.begin()
            with log.open("a", encoding="utf-8") as stream:
                stream.write("[WRN] 队伍匹配回退\n一条龙和配置组任务结束\n")
            self.assertEqual(classifier.classify(process_result(), snapshot), AdapterExecutionStatus.SUCCESS)

    def test_error_with_completion_marker_is_unknown(self):
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "bettergi.log"
            log.write_text("", encoding="utf-8")
            classifier = BetterGIResultClassifier(log)
            snapshot = classifier.begin()
            log.write_text("[ERR] simulated\n一条龙和配置组任务结束\n", encoding="utf-8")
            self.assertEqual(classifier.classify(process_result(), snapshot), AdapterExecutionStatus.UNKNOWN)

    def test_interruption_is_failed_even_if_completion_marker_also_exists(self):
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "bettergi.log"
            log.write_text("", encoding="utf-8")
            classifier = BetterGIResultClassifier(log)
            snapshot = classifier.begin()
            log.write_text("任务中断\n一条龙和配置组任务结束\n", encoding="utf-8")
            self.assertEqual(classifier.classify(process_result(), snapshot), AdapterExecutionStatus.FAILED)

    def test_missing_marker_and_missing_log_are_unknown(self):
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "bettergi.log"
            log.write_text("startup only\n", encoding="utf-8")
            classifier = BetterGIResultClassifier(log)
            snapshot = classifier.begin()
            log.write_text("more startup output\n", encoding="utf-8")
            self.assertEqual(classifier.classify(process_result(), snapshot), AdapterExecutionStatus.UNKNOWN)
        self.assertEqual(BetterGIResultClassifier(None).classify(process_result(), None), AdapterExecutionStatus.UNKNOWN)

    def test_truncated_log_is_unknown(self):
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "bettergi.log"
            log.write_text("a long previous log record", encoding="utf-8")
            classifier = BetterGIResultClassifier(log)
            snapshot = classifier.begin()
            log.write_text("", encoding="utf-8")
            self.assertEqual(classifier.classify(process_result(), snapshot), AdapterExecutionStatus.UNKNOWN)

    def test_nonzero_exit_is_failed_not_success(self):
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "bettergi.log"
            log.write_text("", encoding="utf-8")
            classifier = BetterGIResultClassifier(log)
            snapshot = classifier.begin()
            log.write_text("一条龙和配置组任务结束", encoding="utf-8")
            self.assertEqual(classifier.classify(process_result(code=1), snapshot), AdapterExecutionStatus.FAILED)

    def test_adapter_takes_log_snapshot_before_running_process(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            executable = root / "BetterGI.exe"
            executable.touch()
            log = root / "bettergi.log"
            log.write_text("historical 一条龙和配置组任务结束\n", encoding="utf-8")

            def append_run_marker():
                with log.open("a", encoding="utf-8") as stream:
                    stream.write("一条龙和配置组任务结束\n")

            adapter = BetterGIAdapter(
                GameToolConfig(executable=str(executable),
                               arguments=("--startOneDragon", "默认配置"),
                               result_log_file=str(log)),
                process_runner=FakeRunner(process_result(), append_run_marker),
            )
            self.assertEqual(adapter.execute_daily().status, AdapterExecutionStatus.SUCCESS)


class March7thClassifierTests(unittest.TestCase):
    def setUp(self):
        self.classifier = March7thResultClassifier()

    def classify(self, record, *, code=0):
        stdout = json.dumps(record, ensure_ascii=False) if record is not None else ""
        return self.classifier(process_result(code=code, stdout=stdout))

    def test_verified_daily_success_record(self):
        self.assertEqual(self.classify(m7_record()), AdapterExecutionStatus.SUCCESS)

    def test_explicit_failed_record_requires_matching_nonzero_exit(self):
        record = m7_record(status="failed", exit_code=1, error="task failed")
        self.assertEqual(self.classify(record, code=1), AdapterExecutionStatus.FAILED)
        self.assertEqual(self.classify(record, code=0), AdapterExecutionStatus.UNKNOWN)

    def test_aborted_record_is_unknown_and_not_retry_evidence(self):
        record = m7_record(status="aborted", exit_code=None, error="aborted")
        self.assertEqual(self.classify(record), AdapterExecutionStatus.UNKNOWN)

    def test_uac_cancel_exit_code_is_failed_even_without_record(self):
        self.assertEqual(self.classify(None, code=5), AdapterExecutionStatus.FAILED)

    def test_zero_exit_without_json_record_is_unknown(self):
        self.assertEqual(self.classify(None, code=0), AdapterExecutionStatus.UNKNOWN)

    def test_mismatched_record_code_is_unknown(self):
        self.assertEqual(self.classify(m7_record(exit_code=1), code=0), AdapterExecutionStatus.UNKNOWN)

    def test_unacquired_lock_is_unknown(self):
        self.assertEqual(self.classify(m7_record(lock="busy")), AdapterExecutionStatus.UNKNOWN)

    def test_malformed_final_json_line_is_unknown(self):
        stdout = json.dumps(m7_record()) + "\n{broken"
        self.assertEqual(self.classifier(process_result(stdout=stdout)), AdapterExecutionStatus.UNKNOWN)

    def test_wrong_task_or_invalid_timestamps_are_unknown(self):
        self.assertEqual(self.classify(m7_record(task="routine")), AdapterExecutionStatus.UNKNOWN)
        self.assertEqual(self.classify(m7_record(ended_at="not-a-date")), AdapterExecutionStatus.UNKNOWN)


class AdapterWiringTests(unittest.TestCase):
    def test_march7th_uses_structured_classifier_by_default(self):
        adapter = March7thAdapter(GameToolConfig())
        result = adapter.identify_result(process_result(code=0))
        self.assertEqual(result.status, AdapterExecutionStatus.UNKNOWN)
        self.assertIn("configured tool-specific", result.detail or "")

    def test_bettergi_without_log_path_remains_unknown(self):
        adapter = BetterGIAdapter(GameToolConfig())
        result = adapter.identify_result(process_result(code=0))
        self.assertEqual(result.status, AdapterExecutionStatus.UNKNOWN)


if __name__ == "__main__":
    unittest.main()
