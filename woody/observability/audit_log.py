"""
Audit Log — Structured, persistent log of every Woody action.

Every tool call, its inputs, outputs, and the confirmation decision
are stored locally in SQLite. Provides full transparency and undo capability.

Viewable in the "Woody Activity" panel in the UI.
"""
from __future__ import annotations

import json
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

from woody.utils.logging import get_logger

log = get_logger(__name__)


class AuditLog:
    """
    Persistent audit log backed by SQLite.

    Usage:
        audit = AuditLog(path="~/.Woody/audit.db")
        audit.open()
        audit.log_action(
            session_id="abc",
            tool_name="open_app",
            inputs={"app_name": "Notepad"},
            output={"success": True},
            permission_tier="read_only",
        )
        entries = audit.get_recent(n=20)
    """

    def __init__(
        self,
        path: str | Path = "~/.Woody/audit.db",
        max_entries: int = 100_000,
    ) -> None:
        self._path = Path(path).expanduser()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._max_entries = max_entries
        self._conn: sqlite3.Connection | None = None

    def open(self) -> None:
        self._conn = sqlite3.connect(str(self._path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._create_tables()
        log.info("audit.opened", path=str(self._path))

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    def _create_tables(self) -> None:
        assert self._conn
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS audit_entries (
                id              TEXT PRIMARY KEY,
                session_id      TEXT,
                timestamp       REAL NOT NULL,
                tool_name       TEXT NOT NULL,
                plugin_name     TEXT,
                inputs          TEXT,
                output          TEXT,
                permission_tier TEXT,
                confirmed       INTEGER,
                denied          INTEGER DEFAULT 0,
                error           TEXT,
                undoable        INTEGER DEFAULT 0,
                undo_data       TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit_entries(timestamp DESC);
            CREATE INDEX IF NOT EXISTS idx_audit_session ON audit_entries(session_id);
        """)
        self._conn.commit()

    def log_action(
        self,
        tool_name: str,
        inputs: dict,
        output: Any,
        permission_tier: str = "read_only",
        session_id: str = "",
        plugin_name: str = "",
        confirmed: bool | None = None,
        denied: bool = False,
        error: str | None = None,
        undoable: bool = False,
        undo_data: dict | None = None,
    ) -> str:
        """Log a single tool action. Returns the entry ID."""
        entry_id = str(uuid.uuid4())
        assert self._conn
        self._conn.execute(
            """INSERT INTO audit_entries
               (id, session_id, timestamp, tool_name, plugin_name, inputs, output,
                permission_tier, confirmed, denied, error, undoable, undo_data)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                entry_id,
                session_id,
                time.time(),
                tool_name,
                plugin_name,
                json.dumps(inputs)[:2000],
                json.dumps(str(output))[:2000] if output else None,
                permission_tier,
                int(confirmed) if confirmed is not None else None,
                int(denied),
                error,
                int(undoable),
                json.dumps(undo_data) if undo_data else None,
            ),
        )
        self._conn.commit()
        self._trim_if_needed()
        return entry_id

    def log_entry(self, entry: dict) -> str:
        """Generic dict entry logger (for MCP host integration)."""
        return self.log_action(
            tool_name=entry.get("tool", "unknown"),
            inputs=entry.get("inputs", {}),
            output=entry.get("output"),
            permission_tier=entry.get("permission_tier", "read_only"),
            session_id=entry.get("session_id", ""),
            plugin_name=entry.get("plugin", ""),
            confirmed=entry.get("confirmed"),
            denied=bool(entry.get("denied")),
            error=entry.get("error"),
        )

    def get_recent(self, n: int = 20, session_id: str | None = None) -> list[dict]:
        """Return the n most recent audit entries."""
        assert self._conn
        if session_id:
            rows = self._conn.execute(
                "SELECT * FROM audit_entries WHERE session_id=? ORDER BY timestamp DESC LIMIT ?",
                (session_id, n),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM audit_entries ORDER BY timestamp DESC LIMIT ?",
                (n,),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_undoable(self, session_id: str | None = None) -> list[dict]:
        """Return entries that support undo."""
        assert self._conn
        query = "SELECT * FROM audit_entries WHERE undoable=1"
        args: tuple = ()
        if session_id:
            query += " AND session_id=?"
            args = (session_id,)
        query += " ORDER BY timestamp DESC LIMIT 20"
        return [dict(r) for r in self._conn.execute(query, args).fetchall()]

    def get_entry_count(self) -> int:
        assert self._conn
        return self._conn.execute("SELECT COUNT(*) FROM audit_entries").fetchone()[0]

    def _trim_if_needed(self) -> None:
        """Delete oldest entries when over max_entries."""
        count = self.get_entry_count()
        if count > self._max_entries:
            excess = count - self._max_entries
            assert self._conn
            self._conn.execute(
                """DELETE FROM audit_entries WHERE id IN (
                    SELECT id FROM audit_entries ORDER BY timestamp ASC LIMIT ?
                )""",
                (excess,),
            )
            self._conn.commit()
