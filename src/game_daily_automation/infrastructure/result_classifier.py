"""Explicit result classification; exit codes are evidence, not proof of task success."""

from __future__ import annotations

from collections.abc import Callable

from game_daily_automation.domain.enums import AdapterExecutionStatus
from game_daily_automation.domain.models import ProcessResult


EvidencePredicate = Callable[[ProcessResult], bool]


class ProcessResultClassifier:
    """Classify only when caller supplies verified tool-specific evidence rules.

    No default exit-code rule is provided. Predicates should inspect documented,
    stable completion/failure markers or structured result records.
    """

    def __init__(
        self,
        *,
        success_evidence: EvidencePredicate | None = None,
        failure_evidence: EvidencePredicate | None = None,
    ) -> None:
        if success_evidence is None and failure_evidence is None:
            raise ValueError("At least one verified evidence predicate is required.")
        self._success_evidence = success_evidence
        self._failure_evidence = failure_evidence

    def classify(self, result: ProcessResult) -> AdapterExecutionStatus:
        if not result.started:
            return AdapterExecutionStatus.START_FAILED
        if result.timed_out:
            return AdapterExecutionStatus.TIMEOUT
        if result.execution_error:
            return AdapterExecutionStatus.UNKNOWN

        success = bool(self._success_evidence and self._success_evidence(result))
        failure = bool(self._failure_evidence and self._failure_evidence(result))
        if success and not failure:
            return AdapterExecutionStatus.SUCCESS
        if failure and not success:
            return AdapterExecutionStatus.FAILED
        return AdapterExecutionStatus.UNKNOWN
