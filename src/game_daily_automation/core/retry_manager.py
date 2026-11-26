"""Bounded retry policy for one game; never retries uncertain outcomes."""
from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

from game_daily_automation.domain.enums import AdapterExecutionStatus, ExecutionStatus
from game_daily_automation.domain.models import AdapterExecutionResult
from game_daily_automation.infrastructure.state_store import SQLiteStateStore


@dataclass(frozen=True, slots=True)
class GameRunSummary:
    game_name: str
    status: ExecutionStatus
    attempts: int
    detail: str | None = None


class RetryManager:
    """Runs at most two attempts; retry requires explicit safety and an unlocked desktop."""

    def __init__(
        self,
        state_store: SQLiteStateStore,
        *,
        max_attempts: int = 2,
        retry_delay_seconds: int = 60,
        sleep: Callable[[float], None] = time.sleep,
        is_safe_to_retry: Callable[[AdapterExecutionResult], bool] | None = None,
        is_session_unlocked: Callable[[], bool] | None = None,
    ) -> None:
        if max_attempts != 2:
            raise ValueError("Project policy fixes max_attempts at 2")
        if retry_delay_seconds < 0:
            raise ValueError("retry_delay_seconds cannot be negative")
        self._store = state_store
        self._max_attempts = max_attempts
        self._delay = retry_delay_seconds
        self._sleep = sleep
        self._is_safe = is_safe_to_retry or (lambda _result: False)
        self._is_unlocked = is_session_unlocked or (lambda: True)

    @staticmethod
    def _map_status(status: AdapterExecutionStatus) -> ExecutionStatus:
        if status == AdapterExecutionStatus.SUCCESS:
            return ExecutionStatus.SUCCESS
        if status in {
            AdapterExecutionStatus.FAILED,
            AdapterExecutionStatus.START_FAILED,
            AdapterExecutionStatus.NOT_CONFIGURED,
        }:
            return ExecutionStatus.FAILED
        return ExecutionStatus.UNKNOWN

    def _session_ready(self) -> bool:
        try:
            return bool(self._is_unlocked())
        except Exception:
            return False

    def run_game(self, execution_date, game_name: str, adapter) -> GameRunSummary:
        existing = self._store.get_game_state(execution_date, game_name)
        if existing and existing.status == ExecutionStatus.SUCCESS:
            return GameRunSummary(game_name, ExecutionStatus.SUCCESS, existing.attempt_count, "Already succeeded; skipped.")
        if existing and existing.status in {
            ExecutionStatus.UNKNOWN, ExecutionStatus.INTERRUPTED, ExecutionStatus.RUNNING,
        }:
            return GameRunSummary(game_name, existing.status, existing.attempt_count, "Needs evidence review; not retried.")
        manually_approved_retry = bool(
            existing and existing.status == ExecutionStatus.FAILED
            and existing.error_message
            and "[human_safe_to_retry=true]" in existing.error_message
        )
        if existing and existing.status == ExecutionStatus.FAILED and not manually_approved_retry:
            return GameRunSummary(game_name, ExecutionStatus.FAILED, existing.attempt_count, "Previous failure requires an explicit human safe-to-retry approval.")
        if existing and existing.status == ExecutionStatus.FAILED and existing.attempt_count >= self._max_attempts:
            return GameRunSummary(game_name, ExecutionStatus.FAILED, existing.attempt_count, "Attempt limit already reached.")

        last_result = None
        last_status = ExecutionStatus.UNKNOWN
        attempts = existing.attempt_count if existing else 0
        while attempts < self._max_attempts:
            # Recheck immediately before every external side effect, including retries.
            if not self._session_ready():
                return GameRunSummary(
                    game_name, ExecutionStatus.INTERRUPTED, attempts,
                    "Interactive desktop is locked or unavailable; execution deferred until unlock.",
                )
            safe_retry = attempts > 0
            attempt_number = self._store.start_attempt(
                execution_date, game_name, safe_to_retry=safe_retry,
                max_attempts=self._max_attempts,
            )
            attempts = attempt_number
            try:
                result = adapter.execute_daily()
            except Exception as exc:
                self._store.finish_attempt(
                    execution_date, game_name, ExecutionStatus.UNKNOWN,
                    error_message=f"Adapter raised {type(exc).__name__}: {exc}",
                )
                return GameRunSummary(game_name, ExecutionStatus.UNKNOWN, attempts, str(exc))

            last_result = result
            last_status = self._map_status(result.status)
            self._store.finish_attempt(
                execution_date, game_name, last_status,
                error_message=result.detail,
                process_id=result.process_id,
                return_code=result.return_code,
            )
            if last_status != ExecutionStatus.FAILED:
                return GameRunSummary(game_name, last_status, attempts, result.detail)
            if attempts >= self._max_attempts or not self._is_safe(result):
                return GameRunSummary(game_name, ExecutionStatus.FAILED, attempts, result.detail)
            if self._delay:
                self._sleep(self._delay)

        return GameRunSummary(game_name, last_status, attempts, last_result.detail if last_result else None)
