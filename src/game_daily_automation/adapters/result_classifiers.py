"""Version-aware, fail-closed result classifiers for verified external CLI contracts."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from game_daily_automation.domain.enums import AdapterExecutionStatus
from game_daily_automation.domain.models import ProcessResult


@dataclass(frozen=True, slots=True)
class _LogSnapshot:
    path: Path
    offset: int
    device: int | None
    inode: int | None


class BetterGIResultClassifier:
    """Classify only log lines appended during this invocation."""

    SUCCESS_MARKER = "一条龙和配置组任务结束"
    INTERRUPTED_MARKERS = ("任务中断", "任务被取消")

    def __init__(self, log_file: str | Path | None) -> None:
        self._log_file_template = str(log_file) if log_file else ""

    def begin(self) -> _LogSnapshot | None:
        if not self._log_file_template:
            return None
        dated_path = self._log_file_template.replace(
            "{date}", datetime.now().strftime("%Y%m%d")
        )
        path = Path(os.path.expandvars(dated_path)).expanduser()
        try:
            stat = path.stat()
            return _LogSnapshot(path, stat.st_size, stat.st_dev, stat.st_ino)
        except FileNotFoundError:
            return _LogSnapshot(path, 0, None, None)
        except OSError:
            return None

    def classify(self, result: ProcessResult,
                 snapshot: _LogSnapshot | None) -> AdapterExecutionStatus:
        if result.return_code not in (0, None) and not result.timed_out:
            return AdapterExecutionStatus.FAILED
        if result.return_code is None or snapshot is None:
            return AdapterExecutionStatus.UNKNOWN
        try:
            stat = snapshot.path.stat()
            if snapshot.device is not None and (
                stat.st_dev != snapshot.device or stat.st_ino != snapshot.inode
            ):
                return AdapterExecutionStatus.UNKNOWN
            if stat.st_size < snapshot.offset:
                return AdapterExecutionStatus.UNKNOWN
            with snapshot.path.open("rb") as stream:
                stream.seek(snapshot.offset)
                appended = stream.read().decode("utf-8", errors="replace")
        except OSError:
            return AdapterExecutionStatus.UNKNOWN
        if not appended.strip():
            return AdapterExecutionStatus.UNKNOWN
        if any(marker in appended for marker in self.INTERRUPTED_MARKERS):
            return AdapterExecutionStatus.FAILED
        if result.return_code != 0:
            return AdapterExecutionStatus.FAILED
        if "[ERR]" in appended or self.SUCCESS_MARKER not in appended:
            return AdapterExecutionStatus.UNKNOWN
        return AdapterExecutionStatus.SUCCESS


class March7thResultClassifier:
    """Parse the final --json run record emitted by m7a v2026.11.8+."""

    _KNOWN_FAILURE_CODES = {1, 2, 3, 4, 5}

    @staticmethod
    def _last_json_record(stdout: str) -> dict[str, Any] | None:
        lines = [line.strip() for line in stdout.splitlines() if line.strip()]
        if not lines:
            return None
        try:
            value = json.loads(lines[-1])
        except (json.JSONDecodeError, TypeError):
            return None
        return value if isinstance(value, dict) else None

    @staticmethod
    def _valid_common_record(record: dict[str, Any]) -> bool:
        if record.get("schema") != 1 or record.get("task") != "daily":
            return False
        if not isinstance(record.get("run_id"), str) or not record["run_id"].strip():
            return False
        if (isinstance(record.get("pid"), bool) or
                not isinstance(record.get("pid"), int) or record["pid"] <= 0):
            return False
        if record.get("lock") != "acquired":
            return False
        args = record.get("args")
        if not isinstance(args, list) or not {"daily", "--json", "--non-interactive"}.issubset(args):
            return False
        if not isinstance(record.get("version"), str) or not record["version"].strip():
            return False
        try:
            started = datetime.fromisoformat(record["started_at"])
            ended = datetime.fromisoformat(record["ended_at"])
        except (KeyError, TypeError, ValueError):
            return False
        return ended >= started

    def __call__(self, result: ProcessResult) -> AdapterExecutionStatus:
        record = self._last_json_record(result.stdout)
        if record is None:
            if result.return_code in self._KNOWN_FAILURE_CODES:
                return AdapterExecutionStatus.FAILED
            return AdapterExecutionStatus.UNKNOWN
        if not self._valid_common_record(record):
            return AdapterExecutionStatus.UNKNOWN
        record_code = record.get("exit_code")
        if isinstance(record_code, bool) or not isinstance(record_code, int):
            return AdapterExecutionStatus.UNKNOWN
        status = record.get("status")
        if status == "success":
            if (result.return_code == 0 and record_code == 0
                    and record.get("reason") is None and record.get("error") is None):
                return AdapterExecutionStatus.SUCCESS
            return AdapterExecutionStatus.UNKNOWN
        if status == "failed":
            if record_code != 0 and result.return_code == record_code:
                return AdapterExecutionStatus.FAILED
            return AdapterExecutionStatus.UNKNOWN
        return AdapterExecutionStatus.UNKNOWN
