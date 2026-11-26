"""Bounded, logged subprocess lifecycle management."""

from __future__ import annotations

import logging
import os
import signal
import subprocess
import time
from pathlib import Path
from typing import Sequence

from game_daily_automation.domain.models import ProcessResult


class ProcessRunner:
    """Run argv directly, capture both streams, and bound all waits.

    On Windows, timeout cleanup asks taskkill to terminate the process tree.
    On POSIX, each child starts a new session and its process group is killed.
    A final direct-child kill is always attempted as a fallback.
    """

    def __init__(
        self,
        logger: logging.Logger | None = None,
        *,
        cleanup_timeout_seconds: float = 5.0,
    ) -> None:
        if cleanup_timeout_seconds <= 0:
            raise ValueError("cleanup_timeout_seconds must be positive")
        self._logger = logger or logging.getLogger("game_daily_automation.process")
        self._cleanup_timeout_seconds = cleanup_timeout_seconds

    def run(
        self,
        executable: str | Path,
        arguments: Sequence[str],
        *,
        working_directory: str | Path | None = None,
        timeout_seconds: int = 7200,
        environment: dict[str, str] | None = None,
    ) -> ProcessResult:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")

        command = (str(executable), *(str(arg) for arg in arguments))
        cwd = str(working_directory) if working_directory else None
        started_at = time.monotonic()
        creation_kwargs: dict[str, object] = {}
        if os.name == "nt":
            creation_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            creation_kwargs["start_new_session"] = True

        self._logger.info("process.start command=%r cwd=%r timeout=%ss", command, cwd, timeout_seconds)
        try:
            process = subprocess.Popen(
                list(command),
                cwd=cwd,
                env=environment,
                shell=False,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                errors="replace",
                **creation_kwargs,
            )
        except OSError as exc:
            duration = time.monotonic() - started_at
            self._logger.exception("process.start_failed command=%r", command)
            return ProcessResult(
                started=False,
                command=command,
                return_code=None,
                start_error=f"{type(exc).__name__}: {exc}",
                duration_seconds=duration,
            )

        pid = process.pid
        self._logger.info("process.started pid=%s command=%r", pid, command)
        try:
            stdout, stderr = process.communicate(timeout=timeout_seconds)
            duration = time.monotonic() - started_at
            result = ProcessResult(
                started=True, command=command, return_code=process.returncode,
                stdout=stdout or "", stderr=stderr or "", pid=pid,
                duration_seconds=duration,
            )
            self._log_completion(result)
            return result
        except subprocess.TimeoutExpired as exc:
            self._logger.error("process.timeout pid=%s limit=%ss", pid, timeout_seconds)
            stdout, stderr = self._collect_after_timeout(process, exc)
            duration = time.monotonic() - started_at
            result = ProcessResult(
                started=True, command=command, return_code=process.poll(),
                stdout=stdout, stderr=stderr, timed_out=True, pid=pid,
                duration_seconds=duration,
            )
            self._log_completion(result)
            return result
        except Exception as exc:
            self._logger.exception("process.monitor_error pid=%s", pid)
            self._terminate_tree(process)
            self._close_pipes(process)
            return ProcessResult(
                started=True, command=command, return_code=process.poll(),
                execution_error=f"{type(exc).__name__}: {exc}", pid=pid,
                duration_seconds=time.monotonic() - started_at,
            )

    def _collect_after_timeout(
        self, process: subprocess.Popen[str], timeout_error: subprocess.TimeoutExpired
    ) -> tuple[str, str]:
        self._terminate_tree(process)
        try:
            stdout, stderr = process.communicate(timeout=self._cleanup_timeout_seconds)
            return stdout or "", stderr or ""
        except subprocess.TimeoutExpired:
            self._logger.warning("process.tree_cleanup_incomplete pid=%s; killing direct child", process.pid)
            try:
                process.kill()
            except OSError:
                self._logger.exception("process.direct_kill_failed pid=%s", process.pid)
            try:
                stdout, stderr = process.communicate(timeout=1.0)
                return stdout or "", stderr or ""
            except (subprocess.TimeoutExpired, OSError):
                self._close_pipes(process)
                return self._decode_partial(timeout_error.stdout), self._decode_partial(timeout_error.stderr)

    def _terminate_tree(self, process: subprocess.Popen[str]) -> None:
        if process.poll() is not None:
            return
        try:
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                    shell=False, stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    timeout=self._cleanup_timeout_seconds, check=False,
                )
            else:
                os.killpg(process.pid, signal.SIGKILL)
        except (OSError, subprocess.SubprocessError):
            self._logger.exception("process.tree_kill_failed pid=%s", process.pid)
        if process.poll() is None:
            try:
                process.kill()
            except OSError:
                self._logger.exception("process.kill_failed pid=%s", process.pid)

    @staticmethod
    def _decode_partial(value: str | bytes | None) -> str:
        if value is None:
            return ""
        return value.decode(errors="replace") if isinstance(value, bytes) else value

    @staticmethod
    def _close_pipes(process: subprocess.Popen[str]) -> None:
        for stream in (process.stdout, process.stderr, process.stdin):
            if stream is not None:
                try:
                    stream.close()
                except OSError:
                    pass

    def _log_completion(self, result: ProcessResult) -> None:
        self._logger.info(
            "process.finished pid=%s exit_code=%s timeout=%s duration=%.3fs",
            result.pid, result.return_code, result.timed_out, result.duration_seconds,
        )
        if result.stdout:
            self._logger.info("process.stdout pid=%s\n%s", result.pid, result.stdout.rstrip())
        if result.stderr:
            self._logger.warning("process.stderr pid=%s\n%s", result.pid, result.stderr.rstrip())
