from __future__ import annotations

import unittest
from unittest.mock import patch

from game_daily_automation.system.windows_session import (
    SessionState, SessionStatus, inspect_windows_session,
)
from game_daily_automation.system.session_guard import InteractiveSessionGuard


class WindowsSessionTests(unittest.TestCase):
    def test_non_windows_platform_fails_closed(self):
        with patch("game_daily_automation.system.windows_session.os.name", "posix"):
            status = inspect_windows_session()
        self.assertEqual(status.state, SessionState.UNAVAILABLE)
        self.assertFalse(status.can_run_interactive_tasks)

    def test_only_default_desktop_is_allowed(self):
        self.assertTrue(SessionStatus(SessionState.UNLOCKED, 1, "Default").can_run_interactive_tasks)
        self.assertFalse(SessionStatus(SessionState.LOCKED, 1, "Winlogon").can_run_interactive_tasks)
        self.assertFalse(SessionStatus(SessionState.DISCONNECTED).can_run_interactive_tasks)

    def test_guard_blocks_when_probe_raises(self):
        broken = InteractiveSessionGuard(inspect=lambda: (_ for _ in ()).throw(OSError("api")))
        self.assertFalse(broken.can_run())


if __name__ == "__main__":
    unittest.main()
