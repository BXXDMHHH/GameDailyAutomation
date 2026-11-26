"""Windows session and operating-system integration."""

from game_daily_automation.system.session_guard import InteractiveSessionGuard
from game_daily_automation.system.windows_session import (
    SessionState, SessionStatus, inspect_windows_session,
)

__all__ = [
    "InteractiveSessionGuard", "SessionState", "SessionStatus",
    "inspect_windows_session",
]
