"""Daily workflow orchestration: BetterGI first, then March7th, strictly serial."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Callable

from game_daily_automation.core.retry_manager import GameRunSummary, RetryManager
from game_daily_automation.domain.enums import ExecutionStatus, GameKey
from game_daily_automation.infrastructure.state_store import SQLiteStateStore

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class DailyRunSummary:
    execution_date: date
    status: ExecutionStatus
    games: tuple[GameRunSummary, ...]
    skipped_reason: str | None = None


class DailyOrchestrator:
    """Coordinates daily eligibility and ordered execution; no subprocess calls here."""

    def __init__(
        self,
        state_store: SQLiteStateStore,
        bettergi_adapter,
        march7th_adapter,
        *,
        schedule_time: str = "17:00",
        retry_manager: RetryManager | None = None,
        is_session_unlocked: Callable[[], bool] | None = None,
    ) -> None:
        try:
            hour, minute = (int(part) for part in schedule_time.split(":"))
            self._schedule_time = time(hour, minute)
        except (ValueError, TypeError) as exc:
            raise ValueError("schedule_time must use HH:MM") from exc
        self._store = state_store
        self._adapters = {
            GameKey.BETTERGI.value: bettergi_adapter,
            GameKey.MARCH7TH.value: march7th_adapter,
        }
        self._unlocked = is_session_unlocked or (lambda: True)
        self._retry = retry_manager or RetryManager(
            state_store, is_session_unlocked=self._unlocked
        )

    def run_if_due(self, *, now: datetime | None = None) -> DailyRunSummary:
        current = now or datetime.now().astimezone()
        business_date = current.date()
        if current.timetz().replace(tzinfo=None) < self._schedule_time:
            return DailyRunSummary(business_date, ExecutionStatus.PENDING, (), "Daily trigger time has not arrived.")
        if not self._unlocked():
            return DailyRunSummary(business_date, ExecutionStatus.PENDING, (), "Interactive session is locked; waiting for unlock.")

        self._store.ensure_daily_task(business_date)
        daily = self._store.get_daily_task(business_date)
        if daily and daily["status"] == ExecutionStatus.SUCCESS.value:
            return DailyRunSummary(business_date, ExecutionStatus.SUCCESS, (), "Daily workflow already completed.")

        summaries: list[GameRunSummary] = []
        # Fixed order is intentional. No parallel execution is used.
        for game_name in (GameKey.BETTERGI.value, GameKey.MARCH7TH.value):
            summary = self._retry.run_game(business_date, game_name, self._adapters[game_name])
            summaries.append(summary)
            LOGGER.info("Daily game result: date=%s game=%s status=%s attempts=%s",
                        business_date, game_name, summary.status, summary.attempts)

        if all(item.status == ExecutionStatus.SUCCESS for item in summaries):
            self._store.complete_daily_task(business_date)
            overall = ExecutionStatus.SUCCESS
        elif any(item.status == ExecutionStatus.INTERRUPTED for item in summaries):
            overall = ExecutionStatus.INTERRUPTED
        elif any(item.status in {ExecutionStatus.UNKNOWN, ExecutionStatus.RUNNING}
                 for item in summaries):
            overall = ExecutionStatus.UNKNOWN
        else:
            overall = ExecutionStatus.FAILED
        return DailyRunSummary(business_date, overall, tuple(summaries))
