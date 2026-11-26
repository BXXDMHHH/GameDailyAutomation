"""Cross-platform advisory single-instance lock."""

from __future__ import annotations

import os
from pathlib import Path
from types import TracebackType

from game_daily_automation.exceptions import SingleInstanceError


class SingleInstanceLock:
    """Hold an OS-level non-blocking lock for the lifetime of the context."""

    def __init__(self, lock_path: str | Path) -> None:
        self.lock_path = Path(lock_path).expanduser()
        self._file = None

    def acquire(self) -> "SingleInstanceLock":
        if self._file is not None:
            raise SingleInstanceError("This lock instance is already acquired")
        try:
            self.lock_path.parent.mkdir(parents=True, exist_ok=True)
            self._file = self.lock_path.open("a+b")
            self._file.seek(0, os.SEEK_END)
            if self._file.tell() == 0:
                self._file.write(b"0")
                self._file.flush()
            self._file.seek(0)
            if os.name == "nt":
                import msvcrt
                try:
                    msvcrt.locking(self._file.fileno(), msvcrt.LK_NBLCK, 1)
                except OSError as exc:
                    raise SingleInstanceError("Another application instance is already running") from exc
            else:
                import fcntl
                try:
                    fcntl.flock(self._file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                except OSError as exc:
                    raise SingleInstanceError("Another application instance is already running") from exc
            return self
        except (OSError, SingleInstanceError):
            if self._file is not None:
                self._file.close()
                self._file = None
            raise

    def release(self) -> None:
        if self._file is None:
            return
        try:
            self._file.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self._file.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self._file.fileno(), fcntl.LOCK_UN)
        finally:
            self._file.close()
            self._file = None

    def __enter__(self) -> "SingleInstanceLock":
        return self.acquire()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.release()
