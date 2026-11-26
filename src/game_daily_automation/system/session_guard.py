"""Small fail-closed guard shared by scheduler and retry workflow."""

from __future__ import annotations

import logging
from collections.abc import Callable

from game_daily_automation.system.windows_session import inspect_windows_session


class InteractiveSessionGuard:
    def __init__(
        self,
        inspect: Callable = inspect_windows_session,
        logger: logging.Logger | None = None,
    ) -> None:
        self._inspect = inspect
        self._logger = logger or logging.getLogger("game_daily_automation.session")

    def can_run(self) -> bool:
        try:
            status = self._inspect()
            allowed = bool(status.can_run_interactive_tasks)
        except Exception:
            self._logger.exception("interactive_session_probe_failed; execution blocked")
            return False
        if not allowed:
            self._logger.warning(
                "interactive_session_blocked state=%s session_id=%s detail=%s",
                status.state, status.session_id, status.detail,
            )
        else:
            self._logger.info(
                "interactive_session_ready session_id=%s desktop=%s",
                status.session_id, status.desktop_name,
            )
        return allowed
