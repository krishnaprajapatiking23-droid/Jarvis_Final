"""Session persistence (roadmap section 3: Conversation Sessions)."""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

__all__ = ["SessionDatabase", "session_database"]

DB_PATH = os.path.join("data", "sessions.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    surface    TEXT NOT NULL,
    started_at TEXT NOT NULL,
    ended_at   TEXT,
    meta       TEXT
);
CREATE TABLE IF NOT EXISTS turns (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    role       TEXT NOT NULL,
    text       TEXT NOT NULL,
    at         TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS turns_session ON turns(session_id);
"""


class SessionDatabase:
    """Conversation sessions and their turns, stored in SQLite."""

    def __init__(self, path: Optional[str] = None):
        self.path = path or DB_PATH
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.executescript(SCHEMA)
            self._conn.commit()

    def start(self, surface: str = "text", **meta: Any) -> str:
        session_id = "S-" + uuid.uuid4().hex[:10]
        with self._lock:
            self._conn.execute(
                "INSERT INTO sessions(session_id, surface, started_at, meta) "
                "VALUES (?,?,?,?)",
                (session_id, surface,
                 datetime.now().isoformat(timespec="seconds"),
                 json.dumps(meta)))
            self._conn.commit()
        return session_id

    def end(self, session_id: str) -> bool:
        with self._lock:
            cursor = self._conn.execute(
                "UPDATE sessions SET ended_at=? WHERE session_id=? AND ended_at IS NULL",
                (datetime.now().isoformat(timespec="seconds"), session_id))
            self._conn.commit()
            return cursor.rowcount > 0

    def add_turn(self, session_id: str, role: str, text: str) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO turns(session_id, role, text, at) VALUES (?,?,?,?)",
                (session_id, role, str(text)[:8000],
                 datetime.now().isoformat(timespec="seconds")))
            self._conn.commit()

    def turns(self, session_id: str, limit: int = 200) -> List[Dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT role, text, at FROM turns WHERE session_id=? "
                "ORDER BY id DESC LIMIT ?", (session_id, limit)).fetchall()
        return [dict(row) for row in reversed(rows)]

    def sessions(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM sessions ORDER BY started_at DESC LIMIT ?",
                (limit,)).fetchall()
        return [dict(row) for row in rows]

    def active(self, surface: str = "text") -> Optional[str]:
        with self._lock:
            row = self._conn.execute(
                "SELECT session_id FROM sessions WHERE surface=? AND ended_at IS NULL "
                "ORDER BY started_at DESC LIMIT 1", (surface,)).fetchone()
        return row["session_id"] if row else None

    def statistics(self) -> Dict[str, Any]:
        with self._lock:
            sessions = self._conn.execute(
                "SELECT COUNT(*) AS n FROM sessions").fetchone()["n"]
            open_now = self._conn.execute(
                "SELECT COUNT(*) AS n FROM sessions WHERE ended_at IS NULL"
            ).fetchone()["n"]
            turns = self._conn.execute(
                "SELECT COUNT(*) AS n FROM turns").fetchone()["n"]
        return {"sessions": sessions, "open": open_now, "turns": turns}


session_database = SessionDatabase()
