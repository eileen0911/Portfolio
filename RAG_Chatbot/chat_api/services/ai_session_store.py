import sqlite3
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from time import time
from uuid import uuid4


VALID_MESSAGE_ROLES = {"seed", "system", "user", "assistant"}


@dataclass(frozen=True)
class AISessionMessage:
    session_id: str
    run_id: str
    message_index: int
    role: str
    content: str
    created_at: float
    response_id: str | None = None

    @property
    def message_content(self) -> str:
        return f"{self.role}: {self.content}"


class SQLiteAISessionStore:
    def __init__(
        self,
        db_path: str | Path,
        *,
        idle_timeout_seconds: float | None = None,
        clock: Callable[[], float] = time,
    ) -> None:
        self.db_path = Path(db_path)
        self.idle_timeout_seconds = idle_timeout_seconds
        self._clock = clock
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    def initialize(self) -> None:
        with self._connect() as connection:
            self._create_session_table(connection)
            self._rename_legacy_message_table_if_needed(connection)
            self._create_run_table(connection)
            self._create_message_table(connection)
            self._migrate_legacy_messages(connection)

    def append_message(
        self,
        session_id: str,
        role: str,
        content: str | None = None,
        *,
        response_id: str | None = None,
    ) -> AISessionMessage:
        normalized_session_id = self._require_text(session_id, "session_id")
        normalized_role, normalized_content = self._normalize_message(role, content)
        normalized_response_id = response_id.strip() if response_id else None
        now = self._clock()

        with self._connect() as connection:
            self._expire_session_if_idle(connection, normalized_session_id, now)
            run_id = self._ensure_active_run(connection, normalized_session_id, now)
            row = connection.execute(
                """
                SELECT COALESCE(MAX(message_index), -1) + 1
                FROM ai_session_messages
                WHERE run_id = ?
                """,
                (run_id,),
            ).fetchone()
            message_index = int(row[0])
            connection.execute(
                """
                INSERT INTO ai_session_messages (
                    run_id,
                    session_id,
                    message_index,
                    role,
                    content,
                    response_id,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    normalized_session_id,
                    message_index,
                    normalized_role,
                    normalized_content,
                    normalized_response_id,
                    now,
                ),
            )
            self._touch_active_run(connection, normalized_session_id, run_id, now)

        return AISessionMessage(
            session_id=normalized_session_id,
            run_id=run_id,
            message_index=message_index,
            role=normalized_role,
            content=normalized_content,
            response_id=normalized_response_id,
            created_at=now,
        )

    def start_session(self, session_id: str) -> None:
        normalized_session_id = self._require_text(session_id, "session_id")
        now = self._clock()
        with self._connect() as connection:
            self._expire_session_if_idle(connection, normalized_session_id, now)
            run_id = self._ensure_active_run(connection, normalized_session_id, now)
            self._touch_active_run(connection, normalized_session_id, run_id, now)

    def list_messages(self, session_id: str) -> list[AISessionMessage]:
        normalized_session_id = self._require_text(session_id, "session_id")
        now = self._clock()
        with self._connect() as connection:
            self._expire_session_if_idle(connection, normalized_session_id, now)
            session = self._get_session(connection, normalized_session_id)
            if session is None or session["status"] != "active":
                return []
            active_run = self._get_active_run(connection, normalized_session_id)
            if active_run is None:
                return []
            rows = connection.execute(
                """
                SELECT
                    session_id,
                    run_id,
                    message_index,
                    role,
                    content,
                    response_id,
                    created_at
                FROM ai_session_messages
                WHERE run_id = ?
                ORDER BY message_index ASC
                """,
                (str(active_run["run_id"]),),
            ).fetchall()

        return [self._message_from_row(row) for row in rows]

    def mark_session_inactive(self, session_id: str) -> None:
        normalized_session_id = self._require_text(session_id, "session_id")
        now = self._clock()
        with self._connect() as connection:
            self._ensure_session(connection, normalized_session_id, now)
            self._mark_active_run_inactive(connection, normalized_session_id, now)
            connection.execute(
                """
                UPDATE ai_sessions
                SET status = 'inactive', updated_at = ?, inactive_at = ?
                WHERE session_id = ?
                """,
                (now, now, normalized_session_id),
            )

    def is_session_active(self, session_id: str) -> bool:
        normalized_session_id = self._require_text(session_id, "session_id")
        now = self._clock()
        with self._connect() as connection:
            self._expire_session_if_idle(connection, normalized_session_id, now)
            row = self._get_session(connection, normalized_session_id)
        return row is not None and row["status"] == "active"

    def has_session(self, session_id: str) -> bool:
        normalized_session_id = self._require_text(session_id, "session_id")
        with self._connect() as connection:
            row = self._get_session(connection, normalized_session_id)
        return row is not None

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.db_path, timeout=30.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 30000")
        if self.db_path.name != ":memory:":
            connection.execute("PRAGMA journal_mode = WAL")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _create_session_table(self, connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_sessions (
                session_id TEXT PRIMARY KEY,
                status TEXT NOT NULL CHECK(status IN ('active', 'inactive')),
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                inactive_at REAL
            )
            """
        )

    def _create_run_table(self, connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_session_runs (
                run_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('active', 'inactive')),
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                inactive_at REAL,
                FOREIGN KEY (session_id) REFERENCES ai_sessions(session_id)
            )
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_ai_session_runs_session_status
            ON ai_session_runs(session_id, status, updated_at)
            """
        )

    def _create_message_table(self, connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_session_messages (
                run_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                message_index INTEGER NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('seed', 'system', 'user', 'assistant')),
                content TEXT NOT NULL,
                response_id TEXT,
                created_at REAL NOT NULL,
                PRIMARY KEY (run_id, message_index),
                FOREIGN KEY (run_id) REFERENCES ai_session_runs(run_id),
                FOREIGN KEY (session_id) REFERENCES ai_sessions(session_id)
            )
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_ai_session_messages_session_run
            ON ai_session_messages(session_id, run_id, message_index)
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_ai_session_messages_response
            ON ai_session_messages(response_id)
            """
        )

    def _rename_legacy_message_table_if_needed(self, connection: sqlite3.Connection) -> None:
        if not self._table_exists(connection, "ai_session_messages"):
            return
        columns = self._table_columns(connection, "ai_session_messages")
        if {"run_id", "role", "content"}.issubset(columns):
            return
        if self._table_exists(connection, "ai_session_messages_legacy"):
            connection.execute("DROP TABLE ai_session_messages")
        else:
            connection.execute("ALTER TABLE ai_session_messages RENAME TO ai_session_messages_legacy")

    def _migrate_legacy_messages(self, connection: sqlite3.Connection) -> None:
        if not self._table_exists(connection, "ai_session_messages_legacy"):
            return
        migrated = connection.execute("SELECT COUNT(*) FROM ai_session_messages").fetchone()
        if int(migrated[0]) > 0:
            return

        session_rows = connection.execute(
            """
            SELECT DISTINCT session_id
            FROM ai_session_messages_legacy
            ORDER BY session_id ASC
            """
        ).fetchall()
        for row in session_rows:
            session_id = str(row["session_id"])
            now = self._clock()
            session = self._get_session(connection, session_id)
            if session is None:
                connection.execute(
                    """
                    INSERT INTO ai_sessions (session_id, status, created_at, updated_at, inactive_at)
                    VALUES (?, 'inactive', ?, ?, ?)
                    """,
                    (session_id, now, now, now),
                )
                status = "inactive"
                created_at = now
                updated_at = now
                inactive_at = now
            else:
                status = str(session["status"])
                created_at = float(session["created_at"])
                updated_at = float(session["updated_at"])
                inactive_at = float(session["inactive_at"]) if session["inactive_at"] is not None else None

            run_id = uuid4().hex
            connection.execute(
                """
                INSERT INTO ai_session_runs (
                    run_id,
                    session_id,
                    status,
                    created_at,
                    updated_at,
                    inactive_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (run_id, session_id, status, created_at, updated_at, inactive_at),
            )
            message_rows = connection.execute(
                """
                SELECT message_index, message_content
                FROM ai_session_messages_legacy
                WHERE session_id = ?
                ORDER BY message_index ASC
                """,
                (session_id,),
            ).fetchall()
            for message_row in message_rows:
                role, content = self._parse_legacy_message_content(str(message_row["message_content"]))
                connection.execute(
                    """
                    INSERT INTO ai_session_messages (
                        run_id,
                        session_id,
                        message_index,
                        role,
                        content,
                        created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (run_id, session_id, int(message_row["message_index"]), role, content, created_at),
                )

    def _ensure_active_run(
        self,
        connection: sqlite3.Connection,
        session_id: str,
        now: float,
    ) -> str:
        self._ensure_session(connection, session_id, now)
        active_run = self._get_active_run(connection, session_id)
        if active_run is not None:
            return str(active_run["run_id"])

        run_id = uuid4().hex
        connection.execute(
            """
            INSERT INTO ai_session_runs (run_id, session_id, status, created_at, updated_at)
            VALUES (?, ?, 'active', ?, ?)
            """,
            (run_id, session_id, now, now),
        )
        connection.execute(
            """
            UPDATE ai_sessions
            SET status = 'active', updated_at = ?, inactive_at = NULL
            WHERE session_id = ?
            """,
            (now, session_id),
        )
        return run_id

    def _ensure_session(self, connection: sqlite3.Connection, session_id: str, now: float) -> None:
        connection.execute(
            """
            INSERT INTO ai_sessions (session_id, status, created_at, updated_at)
            VALUES (?, 'active', ?, ?)
            ON CONFLICT(session_id) DO NOTHING
            """,
            (session_id, now, now),
        )

    def _touch_active_run(
        self,
        connection: sqlite3.Connection,
        session_id: str,
        run_id: str,
        now: float,
    ) -> None:
        connection.execute(
            """
            UPDATE ai_session_runs
            SET updated_at = ?
            WHERE run_id = ?
            """,
            (now, run_id),
        )
        connection.execute(
            """
            UPDATE ai_sessions
            SET status = 'active', updated_at = ?, inactive_at = NULL
            WHERE session_id = ?
            """,
            (now, session_id),
        )

    def _get_session(self, connection: sqlite3.Connection, session_id: str) -> sqlite3.Row | None:
        return connection.execute(
            """
            SELECT session_id, status, created_at, updated_at, inactive_at
            FROM ai_sessions
            WHERE session_id = ?
            """,
            (session_id,),
        ).fetchone()

    def _get_active_run(self, connection: sqlite3.Connection, session_id: str) -> sqlite3.Row | None:
        return connection.execute(
            """
            SELECT run_id, status, updated_at
            FROM ai_session_runs
            WHERE session_id = ? AND status = 'active'
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            (session_id,),
        ).fetchone()

    def _expire_session_if_idle(
        self,
        connection: sqlite3.Connection,
        session_id: str,
        now: float,
    ) -> None:
        if self.idle_timeout_seconds is None:
            return
        session = self._get_session(connection, session_id)
        if session is None or session["status"] != "active":
            return
        if now - float(session["updated_at"]) <= self.idle_timeout_seconds:
            return
        self._mark_active_run_inactive(connection, session_id, now)
        connection.execute(
            """
            UPDATE ai_sessions
            SET status = 'inactive', updated_at = ?, inactive_at = ?
            WHERE session_id = ?
            """,
            (now, now, session_id),
        )

    def _mark_active_run_inactive(
        self,
        connection: sqlite3.Connection,
        session_id: str,
        now: float,
    ) -> None:
        connection.execute(
            """
            UPDATE ai_session_runs
            SET status = 'inactive', updated_at = ?, inactive_at = ?
            WHERE session_id = ? AND status = 'active'
            """,
            (now, now, session_id),
        )

    def _message_from_row(self, row: sqlite3.Row) -> AISessionMessage:
        return AISessionMessage(
            session_id=str(row["session_id"]),
            run_id=str(row["run_id"]),
            message_index=int(row["message_index"]),
            role=str(row["role"]),
            content=str(row["content"]),
            response_id=str(row["response_id"]) if row["response_id"] is not None else None,
            created_at=float(row["created_at"]),
        )

    def _normalize_message(self, role: str, content: str | None) -> tuple[str, str]:
        if content is None:
            parsed_role, parsed_content = self._parse_legacy_message_content(role)
            return parsed_role, self._require_text(parsed_content, "content")

        normalized_role = self._require_text(role, "role")
        if normalized_role not in VALID_MESSAGE_ROLES:
            raise ValueError(f"role must be one of {sorted(VALID_MESSAGE_ROLES)}, got {normalized_role!r}")
        return normalized_role, self._require_text(content, "content")

    def _parse_legacy_message_content(self, message_content: str) -> tuple[str, str]:
        normalized = self._require_text(message_content, "message_content")
        if normalized.startswith("user: "):
            return "user", normalized.removeprefix("user: ").strip()
        if normalized.startswith("assistant: "):
            return "assistant", normalized.removeprefix("assistant: ").strip()
        if normalized.startswith("seed:\n"):
            return "seed", normalized.removeprefix("seed:\n").strip()
        if normalized.startswith("seed: "):
            return "seed", normalized.removeprefix("seed: ").strip()
        if normalized == "seed":
            return "seed", normalized
        return "seed", normalized

    def _table_exists(self, connection: sqlite3.Connection, table_name: str) -> bool:
        row = connection.execute(
            """
            SELECT 1
            FROM sqlite_master
            WHERE type = 'table' AND name = ?
            """,
            (table_name,),
        ).fetchone()
        return row is not None

    def _table_columns(self, connection: sqlite3.Connection, table_name: str) -> set[str]:
        rows = connection.execute(f"PRAGMA table_info({table_name})").fetchall()
        return {str(row["name"]) for row in rows}

    def _require_text(self, value: str, field_name: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError(f"{field_name} must not be empty")
        return normalized
