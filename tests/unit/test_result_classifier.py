from __future__ import annotations

import unittest

from game_daily_automation.domain.enums import AdapterExecutionStatus
from game_daily_automation.domain.models import ProcessResult
from game_daily_automation.infrastructure.result_classifier import ProcessResultClassifier


class ProcessResultClassifierTests(unittest.TestCase):
    def test_success_requires_explicit_success_evidence(self) -> None:
        classifier = ProcessResultClassifier(
            success_evidence=lambda result: "DAILY_TASK_COMPLETED" in result.stdout
        )
        result = ProcessResult(True, ("tool",), 0, stdout="DAILY_TASK_COMPLETED")
        self.assertEqual(classifier.classify(result), AdapterExecutionStatus.SUCCESS)

    def test_exit_zero_alone_is_unknown(self) -> None:
        classifier = ProcessResultClassifier(
            success_evidence=lambda result: "completed" in result.stdout
        )
        result = ProcessResult(True, ("tool",), 0, stdout="started")
        self.assertEqual(classifier.classify(result), AdapterExecutionStatus.UNKNOWN)

    def test_explicit_failure_evidence(self) -> None:
        classifier = ProcessResultClassifier(
            failure_evidence=lambda result: "TASK_FAILED" in result.stderr
        )
        result = ProcessResult(True, ("tool",), 1, stderr="TASK_FAILED")
        self.assertEqual(classifier.classify(result), AdapterExecutionStatus.FAILED)

    def test_conflicting_evidence_is_unknown(self) -> None:
        classifier = ProcessResultClassifier(
            success_evidence=lambda result: "done" in result.stdout,
            failure_evidence=lambda result: "failed" in result.stderr,
        )
        result = ProcessResult(True, ("tool",), 1, stdout="done", stderr="failed")
        self.assertEqual(classifier.classify(result), AdapterExecutionStatus.UNKNOWN)

    def test_timeout_is_distinct(self) -> None:
        classifier = ProcessResultClassifier(
            success_evidence=lambda result: True
        )
        result = ProcessResult(True, ("tool",), None, timed_out=True)
        self.assertEqual(classifier.classify(result), AdapterExecutionStatus.TIMEOUT)


if __name__ == "__main__":
    unittest.main()
