"""Transactional SQLite persistence for daily task and per-game attempts."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

from game_daily_automation.domain.enums import ExecutionStatus
from game_daily_automation.exceptions import StatePersistenceError


@dataclass(frozen=True, slots=True)
class GameState:
    execution_date: str
    game_name: str
    status: ExecutionStatus
    attempt_count: int
    started_at: str | None
    finished_at: str | None
    error_message: str | None


class SQLiteStateStore:
    """SQLite state store; every mutation is an explicit IMMEDIATE transaction."""

    SCHEMA_VERSION = 1

    def __init__(self, database_path: str | Path, *, busy_timeout_seconds: float = 10.0) -> None:
        self.database_path = Path(database_path).expanduser()
        self.busy_timeout_seconds = busy_timeout_seconds
        if busy_timeout_seconds <= 0:
            raise ValueError("busy_timeout_seconds must be positive")

    def _connect(self) -> sqlite3.Connection:
        try:
            self.database_path.parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(
                self.database_path,
                timeout=self.busy_timeout_seconds,
                isolation_level=None,
            )
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute(f"PRAGMA busy_timeout = {int(self.busy_timeout_seconds * 1000)}")
            return connection
        except (OSError, sqlite3.Error) as exc:
            raise StatePersistenceError(f"Cannot open SQLite state database: {exc}") from exc

    def initialize(self) -> None:
        """Create schema idempotently and enable durable WAL-backed writes."""
        connection = self._connect()
        try:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute("PRAGMA synchronous = FULL")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS daily_tasks (
                    execution_date TEXT PRIMARY KEY,
                    status TEXT NOT NULL CHECK(status IN
                        ('pending','running','success','failed','unknown','interrupted')),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    error_message TEXT
                );

                CREATE TABLE IF NOT EXISTS game_executions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    execution_date TEXT NOT NULL,
                    game_name TEXT NOT NULL CHECK(game_name IN ('bettergi','march7th')),
                    attempt_number INTEGER NOT NULL CHECK(attempt_number BETWEEN 1 AND 2),
                    status TEXT NOT NULL CHECK(status IN
                        ('pending','running','success','failed','unknown','interrupted')),
                    started_at TEXT,
                    finished_at TEXT,
                    error_message TEXT,
                    process_id INTEGER,
                    return_code INTEGER,
                    UNIQUE(execution_date, game_name, attempt_number),
                    FOREIGN KEY(execution_date) REFERENCES daily_tasks(execution_date)
                        ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_game_executions_date_game
                    ON game_executions(execution_date, game_name, attempt_number);
                PRAGMA user_version = 1;
                """
            )
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version != self.SCHEMA_VERSION:
                raise StatePersistenceError(f"Unsupported database schema version: {version}")
        except sqlite3.Error as exc:
            raise StatePersistenceError(f"Cannot initialize SQLite schema: {exc}") from exc
        finally:
            connection.close()

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")

    @staticmethod
    def _date(value: date | str) -> str:
        return value.isoformat() if isinstance(value, date) else date.fromisoformat(value).isoformat()

    def _transaction(self):
        """Context manager factory intentionally kept private to centralize DB errors."""
        return _Transaction(self)

    def ensure_daily_task(self, execution_date: date | str) -> dict:
        day = self._date(execution_date)
        now = self._now()
        with self._transaction() as connection:
            connection.execute(
                """INSERT INTO daily_tasks(execution_date,status,created_at,updated_at)
                   VALUES(?, 'pending', ?, ?) ON CONFLICT(execution_date) DO NOTHING""",
                (day, now, now),
            )
            row = connection.execute(
                "SELECT * FROM daily_tasks WHERE execution_date = ?", (day,)
            ).fetchone()
            return dict(row)

    def get_daily_task(self, execution_date: date | str) -> dict | None:
        day = self._date(execution_date)
        with self._read() as connection:
            row = connection.execute(
                "SELECT * FROM daily_tasks WHERE execution_date = ?", (day,)
            ).fetchone()
            return dict(row) if row else None

    def get_game_state(self, execution_date: date | str, game_name: str) -> GameState | None:
        day = self._date(execution_date)
        self._validate_game(game_name)
        with self._read() as connection:
            row = connection.execute(
                """SELECT execution_date, game_name, status, attempt_number,
                          started_at, finished_at, error_message
                   FROM game_executions WHERE execution_date=? AND game_name=?
                   ORDER BY attempt_number DESC LIMIT 1""",
                (day, game_name),
            ).fetchone()
            return self._game_state(row) if row else None

    def list_game_attempts(self, execution_date: date | str, game_name: str | None = None) -> list[dict]:
        day = self._date(execution_date)
        with self._read() as connection:
            if game_name is None:
                rows = connection.execute(
                    "SELECT * FROM game_executions WHERE execution_date=? ORDER BY game_name, attempt_number",
                    (day,),
                ).fetchall()
            else:
                self._validate_game(game_name)
                rows = connection.execute(
                    "SELECT * FROM game_executions WHERE execution_date=? AND game_name=? ORDER BY attempt_number",
                    (day, game_name),
                ).fetchall()
            return [dict(row) for row in rows]

    def start_attempt(
        self,
        execution_date: date | str,
        game_name: str,
        *,
        safe_to_retry: bool = False,
        max_attempts: int = 2,
    ) -> int:
        """Persist RUNNING before the caller launches any external side effect.

        A second attempt is allowed only after an explicit FAILED state and an
        explicit safe_to_retry=True decision. UNKNOWN/INTERRUPTED are never retried.
        """
        day = self._date(execution_date)
        self._validate_game(game_name)
        if max_attempts != 2:
            raise ValueError("Project policy fixes max_attempts at 2")
        now = self._now()
        with self._transaction() as connection:
            connection.execute(
                """INSERT INTO daily_tasks(execution_date,status,created_at,updated_at)
                   VALUES(?, 'pending', ?, ?) ON CONFLICT(execution_date) DO NOTHING""",
                (day, now, now),
            )
            daily_row = connection.execute(
                "SELECT status FROM daily_tasks WHERE execution_date=?", (day,)
            ).fetchone()
            if daily_row and daily_row["status"] == ExecutionStatus.SUCCESS.value:
                raise StatePersistenceError(f"Daily task already completed on {day}; further runs blocked")
            rows = connection.execute(
                """SELECT attempt_number,status FROM game_executions
                   WHERE execution_date=? AND game_name=? ORDER BY attempt_number""",
                (day, game_name),
            ).fetchall()
            if any(row["status"] == ExecutionStatus.SUCCESS.value for row in rows):
                raise StatePersistenceError(f"{game_name} already succeeded on {day}; duplicate run blocked")
            if rows:
                latest = rows[-1]["status"]
                if latest == ExecutionStatus.RUNNING.value:
                    raise StatePersistenceError(f"{game_name} already has a RUNNING attempt")
                if latest in {ExecutionStatus.UNKNOWN.value, ExecutionStatus.INTERRUPTED.value}:
                    raise StatePersistenceError(
                        f"{game_name} is {latest}; inspect evidence before any retry"
                    )
                if latest != ExecutionStatus.FAILED.value or not safe_to_retry:
                    raise StatePersistenceError(
                        "Retry requires a confirmed FAILED result and safe_to_retry=True"
                    )
            attempt = len(rows) + 1
            if attempt > max_attempts:
                raise StatePersistenceError(f"{game_name} reached the {max_attempts}-attempt limit")
            connection.execute(
                """INSERT INTO game_executions(
                       execution_date,game_name,attempt_number,status,started_at
                   ) VALUES(?,?,?,?,?)""",
                (day, game_name, attempt, ExecutionStatus.RUNNING.value, now),
            )
            connection.execute(
                "UPDATE daily_tasks SET status='running', updated_at=?, error_message=NULL WHERE execution_date=?",
                (now, day),
            )
            return attempt

    def finish_attempt(
        self,
        execution_date: date | str,
        game_name: str,
        status: ExecutionStatus,
        *,
        error_message: str | None = None,
        process_id: int | None = None,
        return_code: int | None = None,
    ) -> None:
        if status not in {
            ExecutionStatus.SUCCESS, ExecutionStatus.FAILED,
            ExecutionStatus.UNKNOWN, ExecutionStatus.INTERRUPTED,
        }:
            raise ValueError("finish status must be SUCCESS, FAILED, UNKNOWN, or INTERRUPTED")
        day = self._date(execution_date)
        self._validate_game(game_name)
        now = self._now()
        with self._transaction() as connection:
            row = connection.execute(
                """SELECT id FROM game_executions
                   WHERE execution_date=? AND game_name=? AND status='running'
                   ORDER BY attempt_number DESC LIMIT 1""",
                (day, game_name),
            ).fetchone()
            if row is None:
                raise StatePersistenceError(f"No RUNNING attempt exists for {game_name} on {day}")
            connection.execute(
                """UPDATE game_executions
                   SET status=?, finished_at=?, error_message=?, process_id=?, return_code=?
                   WHERE id=?""",
                (status.value, now, error_message, process_id, return_code, row["id"]),
            )
            latest_rows = connection.execute(
                """SELECT e.status FROM game_executions AS e
                   JOIN (
                       SELECT game_name, MAX(attempt_number) AS latest_attempt
                       FROM game_executions WHERE execution_date=? GROUP BY game_name
                   ) AS latest
                   ON e.game_name=latest.game_name AND e.attempt_number=latest.latest_attempt
                   WHERE e.execution_date=?""",
                (day, day),
            ).fetchall()
            statuses = {item["status"] for item in latest_rows}
            if ExecutionStatus.UNKNOWN.value in statuses:
                daily_status = ExecutionStatus.UNKNOWN.value
            elif ExecutionStatus.INTERRUPTED.value in statuses:
                daily_status = ExecutionStatus.INTERRUPTED.value
            elif ExecutionStatus.FAILED.value in statuses:
                daily_status = ExecutionStatus.FAILED.value
            else:
                # A single game's success must not imply the whole daily sequence succeeded.
                daily_status = ExecutionStatus.RUNNING.value
            connection.execute(
                "UPDATE daily_tasks SET status=?, updated_at=?, error_message=? WHERE execution_date=?",
                (daily_status, now, error_message, day),
            )

    def complete_daily_task(
        self, execution_date: date | str, *, required_games: tuple[str, ...] = ("bettergi", "march7th")
    ) -> None:
        """Mark the daily sequence successful only after every required game succeeded."""
        day = self._date(execution_date)
        if not required_games:
            raise ValueError("required_games cannot be empty")
        for game in required_games:
            self._validate_game(game)
        now = self._now()
        with self._transaction() as connection:
            row = connection.execute(
                "SELECT status FROM daily_tasks WHERE execution_date=?", (day,)
            ).fetchone()
            if row is None:
                raise StatePersistenceError(f"No daily task exists for {day}")
            for game in required_games:
                latest = connection.execute(
                    """SELECT status FROM game_executions WHERE execution_date=? AND game_name=?
                       ORDER BY attempt_number DESC LIMIT 1""",
                    (day, game),
                ).fetchone()
                if latest is None or latest["status"] != ExecutionStatus.SUCCESS.value:
                    raise StatePersistenceError(
                        f"Cannot complete daily task: {game} has not succeeded"
                    )
            connection.execute(
                "UPDATE daily_tasks SET status='success', updated_at=?, error_message=NULL WHERE execution_date=?",
                (now, day),
            )

    def resolve_unknown(
        self,
        execution_date: date | str,
        game_name: str,
        *,
        confirmed_status: ExecutionStatus,
        evidence_note: str,
        safe_to_retry: bool = False,
    ) -> None:
        """Record a human-reviewed UNKNOWN outcome with an auditable evidence note."""
        if confirmed_status not in {ExecutionStatus.SUCCESS, ExecutionStatus.FAILED}:
            raise ValueError("confirmed_status must be SUCCESS or FAILED")
        if not evidence_note or not evidence_note.strip():
            raise ValueError("evidence_note is required for human confirmation")
        day = self._date(execution_date)
        self._validate_game(game_name)
        note = f"Human confirmed {confirmed_status.value}: {evidence_note.strip()}"
        if confirmed_status == ExecutionStatus.FAILED and safe_to_retry:
            note += " [human_safe_to_retry=true]"
        now = self._now()
        with self._transaction() as connection:
            row = connection.execute(
                """SELECT id FROM game_executions
                   WHERE execution_date=? AND game_name=? AND status='unknown'
                   ORDER BY attempt_number DESC LIMIT 1""",
                (day, game_name),
            ).fetchone()
            if row is None:
                raise StatePersistenceError(f"No UNKNOWN attempt exists for {game_name} on {day}")
            connection.execute(
                """UPDATE game_executions SET status=?, finished_at=?,
                   error_message=? WHERE id=?""",
                (confirmed_status.value, now, note, row["id"]),
            )
            daily_status = (
                ExecutionStatus.RUNNING.value
                if confirmed_status == ExecutionStatus.SUCCESS
                else ExecutionStatus.FAILED.value
            )
            connection.execute(
                """UPDATE daily_tasks SET status=?, updated_at=?, error_message=?
                   WHERE execution_date=?""",
                (daily_status, now, note, day),
            )

    def recover_interrupted(self) -> int:
        """Convert stale RUNNING attempts to UNKNOWN; never schedule a retry."""
        now = self._now()
        with self._transaction() as connection:
            running_count = connection.execute(
                "SELECT COUNT(*) FROM game_executions WHERE status='running'"
            ).fetchone()[0]
            rows = connection.execute(
                "SELECT DISTINCT execution_date FROM game_executions WHERE status='running'"
            ).fetchall()
            connection.execute(
                """UPDATE game_executions
                   SET status='unknown', finished_at=?,
                       error_message=COALESCE(error_message, 'Process state unknown after application restart')
                   WHERE status='running'""",
                (now,),
            )
            for row in rows:
                connection.execute(
                    """UPDATE daily_tasks SET status='unknown', updated_at=?,
                       error_message='Recovered after restart; inspect game/process evidence'
                       WHERE execution_date=?""",
                    (now, row["execution_date"]),
                )
            return running_count

    @staticmethod
    def _validate_game(game_name: str) -> None:
        if game_name not in {"bettergi", "march7th"}:
            raise ValueError(f"Unsupported game name: {game_name}")

    @staticmethod
    def _game_state(row: sqlite3.Row) -> GameState:
        return GameState(
            execution_date=row["execution_date"], game_name=row["game_name"],
            status=ExecutionStatus(row["status"]), attempt_count=row["attempt_number"],
            started_at=row["started_at"], finished_at=row["finished_at"],
            error_message=row["error_message"],
        )

    class _ReadContext:
        def __init__(self, store: "SQLiteStateStore") -> None:
            self.store = store
            self.connection: sqlite3.Connection | None = None
        def __enter__(self):
            self.connection = self.store._connect()
            return self.connection
        def __exit__(self, exc_type, exc, tb):
            assert self.connection is not None
            self.connection.close()

    def _read(self):
        return self._ReadContext(self)


class _Transaction:
    def __init__(self, store: SQLiteStateStore) -> None:
        self.store = store
        self.connection: sqlite3.Connection | None = None

    def __enter__(self) -> sqlite3.Connection:
        self.connection = self.store._connect()
        try:
            self.connection.execute("BEGIN IMMEDIATE")
            return self.connection
        except sqlite3.Error as exc:
            self.connection.close()
            raise StatePersistenceError(f"Cannot begin SQLite transaction: {exc}") from exc

    def __exit__(self, exc_type, exc, tb) -> None:
        assert self.connection is not None
        try:
            if exc_type is None:
                self.connection.commit()
            else:
                self.connection.rollback()
                if exc_type is not None and issubclass(exc_type, sqlite3.Error):
                    raise StatePersistenceError(f"SQLite statement failed: {exc}") from exc
        except sqlite3.Error as db_exc:
            self.connection.rollback()
            raise StatePersistenceError(f"SQLite transaction failed: {db_exc}") from db_exc
        finally:
            self.connection.close()
