"""Shared implementation for configured command-line adapters."""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path

from game_daily_automation.config.loader import GameToolConfig
from game_daily_automation.domain.enums import AdapterExecutionStatus, GameKey
from game_daily_automation.domain.models import (
    AdapterAvailability, AdapterExecutionResult, ProcessResult,
)
from game_daily_automation.infrastructure.process_runner import ProcessRunner

ResultClassifier = Callable[[ProcessResult], AdapterExecutionStatus]


class ConfiguredGameAdapter:
    """Common process mechanics; subclasses supply identity, not global ordering."""

    def __init__(
        self,
        game_key: GameKey,
        config: GameToolConfig,
        process_runner: ProcessRunner | None = None,
        result_classifier: ResultClassifier | None = None,
    ) -> None:
        self._game_key = game_key
        self._config = config
        self._process_runner = process_runner or ProcessRunner()
        self._result_classifier = result_classifier

    @property
    def game_key(self) -> GameKey:
        return self._game_key

    def _executable_path(self) -> Path:
        return (
            Path(os.path.expandvars(self._config.executable)).expanduser()
            if self._config.executable else Path()
        )

    def _working_directory(self) -> str | None:
        if not self._config.working_directory:
            return None
        return os.path.expandvars(self._config.working_directory)

    def check_available(self) -> AdapterAvailability:
        executable = self._executable_path()
        configured = self._config.enabled and bool(self._config.executable.strip())
        exists = configured and executable.is_file()
        probe_code: int | None = None
        probe_output = ""
        error = None

        if not self._config.enabled:
            error = "Adapter is disabled in configuration."
        elif configured and not exists:
            error = f"Executable does not exist or is not a file: {executable}"
        elif exists and self._config.version_arguments:
            probe = self._process_runner.run(
                executable,
                self._config.version_arguments,
                working_directory=self._working_directory(),
                timeout_seconds=min(self._config.timeout_seconds, 30),
            )
            probe_code = probe.return_code
            probe_output = (probe.stdout + probe.stderr).strip()
            if not probe.started:
                error = probe.start_error
            elif probe.timed_out:
                error = "Configured version probe timed out."
            elif probe.return_code != 0:
                error = f"Configured version probe returned exit code {probe.return_code}."

        return AdapterAvailability(
            game=self._game_key,
            executable_path=str(executable) if configured else "",
            executable_exists=exists,
            configured=configured,
            version_probe_configured=bool(self._config.version_arguments),
            version_probe_return_code=probe_code,
            version_output=probe_output,
            error=error,
        )

    def execute_daily(self) -> AdapterExecutionResult:
        availability = self.check_available()
        if not availability.available:
            return AdapterExecutionResult(
                game=self._game_key,
                status=AdapterExecutionStatus.NOT_CONFIGURED,
                detail=availability.error or "Executable path is not configured.",
            )
        if not self._config.arguments:
            return AdapterExecutionResult(
                game=self._game_key,
                status=AdapterExecutionStatus.NOT_CONFIGURED,
                detail="Daily-task arguments are empty; configure only after local verification.",
            )

        process_result = self._process_runner.run(
            self._config.executable,
            self._config.arguments,
            working_directory=self._working_directory(),
            timeout_seconds=self._config.timeout_seconds,
        )
        return self.identify_result(process_result)

    def identify_result(self, process_result: ProcessResult) -> AdapterExecutionResult:
        if not process_result.started:
            return AdapterExecutionResult(
                game=self._game_key,
                status=AdapterExecutionStatus.START_FAILED,
                detail=process_result.start_error or "Process could not be started.",
            )
        if process_result.timed_out:
            return AdapterExecutionResult(
                game=self._game_key,
                status=AdapterExecutionStatus.UNKNOWN,
                return_code=process_result.return_code,
                stdout=process_result.stdout,
                stderr=process_result.stderr,
                detail="Process timed out; verify task state and logs before any recovery action.",
            )

        status = AdapterExecutionStatus.UNKNOWN
        detail = (
            "No verified result classifier is configured. "
            "Process exit code alone is not treated as task success."
        )
        if self._result_classifier is not None:
            classified = self._result_classifier(process_result)
            if classified not in {
                AdapterExecutionStatus.SUCCESS,
                AdapterExecutionStatus.FAILED,
                AdapterExecutionStatus.UNKNOWN,
            }:
                raise ValueError("Result classifier returned an unsupported status.")
            status = classified
            detail = "Classified using the configured tool-specific result classifier."

        return AdapterExecutionResult(
            game=self._game_key,
            status=status,
            return_code=process_result.return_code,
            stdout=process_result.stdout,
            stderr=process_result.stderr,
            detail=detail,
        )
