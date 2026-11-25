"""Shared safe subprocess execution primitive."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Sequence

from game_daily_automation.domain.models import ProcessResult


def _as_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode(errors="replace")
    return value


class ProcessRunner:
    """Run a process with an argv list and shell disabled.

    Text output uses the host's locale encoding because Windows console tools
    do not all emit UTF-8. The application log layer remains UTF-8.
    """

    def run(
        self,
        executable: str | Path,
        arguments: Sequence[str],
        *,
        working_directory: str | Path | None = None,
        timeout_seconds: int = 7200,
    ) -> ProcessResult:
        command = (str(executable), *(str(arg) for arg in arguments))
        cwd = str(working_directory) if working_directory else None
        try:
            completed = subprocess.run(
                list(command),
                cwd=cwd,
                shell=False,
                check=False,
                capture_output=True,
                text=True,
                errors="replace",
                timeout=timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            return ProcessResult(
                started=True,
                command=command,
                return_code=None,
                stdout=_as_text(exc.stdout),
                stderr=_as_text(exc.stderr),
                timed_out=True,
            )
        except OSError as exc:
            return ProcessResult(
                started=False,
                command=command,
                return_code=None,
                start_error=f"{type(exc).__name__}: {exc}",
            )

        return ProcessResult(
            started=True,
            command=command,
            return_code=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )
