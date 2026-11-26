"""Windows application bootstrap and one-shot scheduled execution."""

from __future__ import annotations

import logging
import sys
from collections.abc import Sequence

from game_daily_automation.adapters import BetterGIAdapter, March7thAdapter
from game_daily_automation.adapters.result_classifiers import (
    BetterGIResultClassifier, March7thResultClassifier,
)
from game_daily_automation.cli import build_parser
from game_daily_automation.config.loader import ConfigError, load_config
from game_daily_automation.core.orchestrator import DailyOrchestrator
from game_daily_automation.core.retry_manager import RetryManager
from game_daily_automation.infrastructure.logging_config import configure_logging
from game_daily_automation.infrastructure.single_instance import SingleInstanceLock
from game_daily_automation.infrastructure.state_store import SQLiteStateStore
from game_daily_automation.system.session_guard import InteractiveSessionGuard
from game_daily_automation.system.windows_session import inspect_windows_session


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        config = load_config(args.config)
        logger = configure_logging(config)
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"Unable to initialize logging: {exc}", file=sys.stderr)
        return 2

    if args.check_session:
        status = inspect_windows_session()
        print(f"session={status.state.value} session_id={status.session_id} desktop={status.desktop_name or '-'}")
        if status.detail:
            print(status.detail)
        return 0 if status.can_run_interactive_tasks else 3

    if sys.platform != "win32":
        logger.error("Scheduled game automation is supported only on Windows.")
        return 3

    lock_path = config.storage.database_file_path.with_suffix(".lock")
    try:
        with SingleInstanceLock(lock_path):
            store = SQLiteStateStore(config.storage.database_file_path)
            store.initialize()
            recovered = store.recover_interrupted()
            if recovered:
                logger.warning(
                    "Recovered %s stale RUNNING attempt(s) as UNKNOWN. "
                    "No games will launch until the external process state is reviewed.",
                    recovered,
                )
                return 0
            if store.has_unresolved_recovery():
                logger.warning(
                    "A prior crash-recovered attempt is still awaiting evidence review; "
                    "all new game launches remain blocked."
                )
                return 0

            guard = InteractiveSessionGuard(logger=logger)
            if not guard.can_run():
                logger.info("No game task launched; the next scheduled/logon/unlock trigger will check again.")
                return 0

            retry = RetryManager(
                store,
                retry_delay_seconds=config.execution.retry_delay_seconds,
                # Keep automatic retries disabled until safe retry rules have
                # separate, tool-specific evidence and explicit approval.
                is_session_unlocked=guard.can_run,
            )
            orchestrator = DailyOrchestrator(
                store,
                BetterGIAdapter(
                    config.bettergi,
                    result_classifier=BetterGIResultClassifier(config.bettergi.result_log_file),
                ),
                March7thAdapter(
                    config.march7th,
                    result_classifier=March7thResultClassifier(),
                ),
                schedule_time=config.schedule.time,
                retry_manager=retry,
                is_session_unlocked=guard.can_run,
            )
            summary = orchestrator.run_if_due()
            logger.info(
                "Daily scheduler finished date=%s status=%s detail=%s",
                summary.execution_date, summary.status.value, summary.skipped_reason,
            )
            for game in summary.games:
                logger.info("Game result name=%s status=%s attempts=%s detail=%s",
                            game.game_name, game.status.value, game.attempts, game.detail)
            return 0
    except Exception:
        logger.exception("Scheduler startup or execution failed.")
        return 1
