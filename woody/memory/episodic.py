"""
Episodic Memory — SQLite session log with sqlite-vec vector search.

Stores past sessions/tasks with outcomes so Woody can recall
"like last time" context and avoid repeating failed approaches.

Schema:
  sessions: id, timestamp, user_request, intent, result_summary, success, duration_ms
  tool_calls: id, session_id, tool_name, inputs_json, output_json, tier, confirmed, timestamp

Vector embeddings stored in sqlite-vec for semantic recall.
"""
from __future__ import annotations

import json
import sqlite3
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from woody.utils.logging import get_logger

log = get_logger(__name__)


@dataclass
class SessionRecord:
    session_id: str
    timestamp: float
    user_request: str
    intent: str
    result_summary: str
    success: bool
    duration_ms: float
    tool_call_count: int = 0


class EpisodicMemory:
    """
    Persistent episodic memory backed by SQLite.

    Usage:
        mem = EpisodicMemory(db_path="~/.Woody/episodic.db")
        mem.open()
        mem.log_session(session_id="abc", user_request="Open Notepad", ...)
        history = mem.get_recent(n=5)
        similar = mem.search_similar("open a text editor", n=3)
    """

    def __init__(self, db_path: str | Path = "~/.Woody/episodic.db") -> None:
        self._db_path = Path(db_path).expanduser()
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: sqlite3.Connection | None = None
        self._has_vec = False

    def open(self) -> None:
        """Open the database and create tables if needed."""
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._create_tables()
        self._try_load_vec()
        log.info("episodic.opened", path=str(self._db_path))

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    def _create_tables(self) -> None:
        assert self._conn
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS sessions (
                id          TEXT PRIMARY KEY,
                timestamp   REAL NOT NULL,
                user_request TEXT NOT NULL,
                intent      TEXT,
                result_summary TEXT,
                success     INTEGER DEFAULT 1,
                duration_ms REAL DEFAULT 0,
                tool_calls  INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS tool_calls (
                id          TEXT PRIMARY KEY,
                session_id  TEXT NOT NULL,
                tool_name   TEXT NOT NULL,
                inputs      TEXT,
                output      TEXT,
                tier        TEXT,
                confirmed   INTEGER,
                timestamp   REAL,
                FOREIGN KEY (session_id) REFERENCES sessions(id)
            );

            CREATE INDEX IF NOT EXISTS idx_sessions_ts ON sessions(timestamp);
            CREATE INDEX IF NOT EXISTS idx_tool_session ON tool_calls(session_id);
        """)
        self._conn.commit()

    def _try_load_vec(self) -> None:
        """Try to load sqlite-vec extension for vector search."""
        try:
            import sqlite_vec
            assert self._conn
            self._conn.enable_load_extension(True)
            sqlite_vec.load(self._conn)
            self._conn.enable_load_extension(False)

            # Create vector table for session embeddings
            self._conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS session_embeddings
                USING vec0(session_id TEXT, embedding FLOAT[384])
            """)
            self._conn.commit()
            self._has_vec = True
            log.info("episodic.vec_loaded")
        except Exception as e:
            log.debug("episodic.vec_unavailable", reason=str(e), fallback="text_search")

    def log_session(
        self,
        session_id: str,
        user_request: str,
        intent: str = "",
        result_summary: str = "",
        success: bool = True,
        duration_ms: float = 0.0,
        tool_call_count: int = 0,
    ) -> None:
        """Log a completed session."""
        assert self._conn
        self._conn.execute(
            """INSERT OR REPLACE INTO sessions
               (id, timestamp, user_request, intent, result_summary, success, duration_ms, tool_calls)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (session_id, time.time(), user_request, intent, result_summary,
             int(success), duration_ms, tool_call_count),
        )
        self._conn.commit()

    def log_tool_call(
        self,
        session_id: str,
        tool_name: str,
        inputs: dict,
        output: Any,
        tier: str = "read_only",
        confirmed: bool | None = None,
    ) -> None:
        """Log a single tool call within a session."""
        assert self._conn
        self._conn.execute(
            """INSERT INTO tool_calls
               (id, session_id, tool_name, inputs, output, tier, confirmed, timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (str(uuid.uuid4()), session_id, tool_name,
             json.dumps(inputs)[:2000],
             json.dumps(str(output))[:2000],
             tier,
             int(confirmed) if confirmed is not None else None,
             time.time()),
        )
        self._conn.commit()

    def get_recent(self, n: int = 5) -> list[dict]:
        """Return the n most recent sessions."""
        assert self._conn
        rows = self._conn.execute(
            "SELECT * FROM sessions ORDER BY timestamp DESC LIMIT ?", (n,)
        ).fetchall()
        return [dict(r) for r in rows]

    def format_history_for_prompt(self, n: int = 3) -> str:
        """Format recent session history for inclusion in the planner prompt."""
        sessions = self.get_recent(n=n)
        if not sessions:
            return ""
        lines = []
        for s in sessions:
            import datetime
            ts = datetime.datetime.fromtimestamp(s["timestamp"]).strftime("%H:%M")
            status = "✓" if s["success"] else "✗"
            lines.append(f"{status} [{ts}] {s['user_request']} → {s['result_summary'][:80]}")
        return "\n".join(lines)

    def get_session_count(self) -> int:
        assert self._conn
        return self._conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
