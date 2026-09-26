"""
==========================================
JARVIS PRO
Conversation Store  (SQLite persistence)
==========================================

Additive persistence layer for the Conversation System.

This module creates and owns ONLY ``data/conversation.db``.
Existing databases (jarvis.db, visitors.db, memory_v2.db, brain_v2.db)
are never opened or modified by this module.

All public functions degrade gracefully: if SQLite is unavailable or a
query fails, the error is logged and a safe default is returned so that
a conversation-persistence problem can never crash JARVIS.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

log = logging.getLogger("jarvis.conversation.store")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DATABASE = DATA_DIR / "conversation.db"

_LOCK = threading.RLock()
_READY = False


# ------------------------------------------------------------------
# connection helpers
# ------------------------------------------------------------------
def connect() -> sqlite3.Connection:
    """Open a connection to the conversation database."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DATABASE), timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


SCHEMA: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS conversation_sessions(
        session_id      TEXT PRIMARY KEY,
        user            TEXT,
        mode            TEXT,
        started_at      TEXT,
        ended_at        TEXT,
        last_active_at  TEXT,
        message_count   INTEGER DEFAULT 0,
        active_topic    TEXT,
        summary         TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS conversation_messages(
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id      TEXT,
        conversation_id TEXT,
        turn            INTEGER,
        role            TEXT,
        text            TEXT,
        intent          TEXT,
        topic           TEXT,
        emotion         TEXT,
        entities        TEXT,
        created_at      TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS conversation_context(
        session_id      TEXT PRIMARY KEY,
        state           TEXT,
        updated_at      TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS conversation_entities(
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id      TEXT,
        name            TEXT,
        type            TEXT,
        aliases         TEXT,
        context         TEXT,
        first_mention   TEXT,
        last_mention    TEXT,
        mention_count   INTEGER DEFAULT 1,
        UNIQUE(session_id, name, type)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS conversation_topics(
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id      TEXT,
        topic           TEXT,
        started_at      TEXT,
        last_seen_at    TEXT,
        message_count   INTEGER DEFAULT 1,
        UNIQUE(session_id, topic)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS conversation_summaries(
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id      TEXT,
        summary         TEXT,
        covers_from     INTEGER,
        covers_to       INTEGER,
        created_at      TEXT
    )
    """,
)

INDEXES: tuple[str, ...] = (
    "CREATE INDEX IF NOT EXISTS idx_msg_session ON conversation_messages(session_id, id)",
    "CREATE INDEX IF NOT EXISTS idx_msg_created ON conversation_messages(created_at)",
    "CREATE INDEX IF NOT EXISTS idx_msg_topic   ON conversation_messages(topic)",
    "CREATE INDEX IF NOT EXISTS idx_ent_session ON conversation_entities(session_id, last_mention)",
    "CREATE INDEX IF NOT EXISTS idx_ent_name    ON conversation_entities(name)",
    "CREATE INDEX IF NOT EXISTS idx_top_session ON conversation_topics(session_id, last_seen_at)",
    "CREATE INDEX IF NOT EXISTS idx_sum_session ON conversation_summaries(session_id, id)",
    "CREATE INDEX IF NOT EXISTS idx_ses_active  ON conversation_sessions(last_active_at)",
)


def create_tables() -> bool:
    """Create tables and indexes if they do not exist. Safe to call often."""
    global _READY
    with _LOCK:
        if _READY:
            return True
        try:
            conn = connect()
            try:
                cur = conn.cursor()
                for statement in SCHEMA:
                    cur.execute(statement)
                for statement in INDEXES:
                    cur.execute(statement)
                conn.commit()
            finally:
                conn.close()
            _READY = True
            return True
        except Exception as error:  # pragma: no cover - defensive
            log.warning("conversation store init failed: %s", error)
            return False


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _execute(query: str, params: Iterable[Any] = ()) -> Optional[int]:
    """Run a write query. Returns lastrowid or None on failure."""
    if not create_tables():
        return None
    with _LOCK:
        try:
            conn = connect()
            try:
                cur = conn.cursor()
                cur.execute(query, tuple(params))
                conn.commit()
                return cur.lastrowid
            finally:
                conn.close()
        except Exception as error:
            log.warning("conversation store write failed: %s", error)
            return None


def _query(query: str, params: Iterable[Any] = ()) -> List[Dict[str, Any]]:
    """Run a read query. Returns [] on failure."""
    if not create_tables():
        return []
    with _LOCK:
        try:
            conn = connect()
            try:
                cur = conn.cursor()
                cur.execute(query, tuple(params))
                return [dict(row) for row in cur.fetchall()]
            finally:
                conn.close()
        except Exception as error:
            log.warning("conversation store read failed: %s", error)
            return []


def _dumps(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, default=str)
    except Exception:
        return "null"


def _loads(value: Any, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except Exception:
        return default


# ------------------------------------------------------------------
# sessions
# ------------------------------------------------------------------
def start_session(session_id: str, user: str = "", mode: str = "text") -> None:
    now = _now()
    _execute(
        """
        INSERT OR IGNORE INTO conversation_sessions
            (session_id, user, mode, started_at, last_active_at, message_count)
        VALUES (?, ?, ?, ?, ?, 0)
        """,
        (session_id, user, mode, now, now),
    )


def touch_session(session_id: str, active_topic: Optional[str] = None) -> None:
    _execute(
        """
        UPDATE conversation_sessions
           SET last_active_at = ?,
               active_topic   = COALESCE(?, active_topic)
         WHERE session_id = ?
        """,
        (_now(), active_topic, session_id),
    )


def end_session(session_id: str, summary: str = "") -> None:
    _execute(
        """
        UPDATE conversation_sessions
           SET ended_at = ?,
               summary  = CASE WHEN ? = '' THEN summary ELSE ? END
         WHERE session_id = ?
        """,
        (_now(), summary, summary, session_id),
    )


def get_session(session_id: str) -> Optional[Dict[str, Any]]:
    rows = _query(
        "SELECT * FROM conversation_sessions WHERE session_id = ?", (session_id,)
    )
    return rows[0] if rows else None


def last_session(exclude: str = "") -> Optional[Dict[str, Any]]:
    """Most recently active session, optionally excluding the current one."""
    rows = _query(
        """
        SELECT * FROM conversation_sessions
         WHERE session_id != ?
         ORDER BY last_active_at DESC
         LIMIT 1
        """,
        (exclude,),
    )
    return rows[0] if rows else None


def sessions(limit: int = 20) -> List[Dict[str, Any]]:
    return _query(
        "SELECT * FROM conversation_sessions ORDER BY last_active_at DESC LIMIT ?",
        (limit,),
    )


# ------------------------------------------------------------------
# messages
# ------------------------------------------------------------------
def add_message(
    session_id: str,
    role: str,
    text: str,
    conversation_id: str = "",
    turn: int = 0,
    intent: str = "",
    topic: str = "",
    emotion: str = "",
    entities: Optional[List[Dict[str, Any]]] = None,
) -> Optional[int]:
    row_id = _execute(
        """
        INSERT INTO conversation_messages
            (session_id, conversation_id, turn, role, text,
             intent, topic, emotion, entities, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            session_id,
            conversation_id,
            turn,
            role,
            text,
            intent,
            topic,
            emotion,
            _dumps(entities or []),
            _now(),
        ),
    )
    if row_id is not None:
        _execute(
            """
            UPDATE conversation_sessions
               SET message_count = message_count + 1,
                   last_active_at = ?
             WHERE session_id = ?
            """,
            (_now(), session_id),
        )
    return row_id


def recent_messages(session_id: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Most recent messages of a session, oldest-first."""
    rows = _query(
        """
        SELECT * FROM conversation_messages
         WHERE session_id = ?
         ORDER BY id DESC
         LIMIT ?
        """,
        (session_id, limit),
    )
    rows.reverse()
    for row in rows:
        row["entities"] = _loads(row.get("entities"), [])
    return rows


def search_messages(
    keywords: Iterable[str],
    limit: int = 20,
    session_id: Optional[str] = None,
    exclude_session: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Keyword search across stored messages (relevance handled upstream)."""
    terms = [term for term in {k.strip().lower() for k in keywords} if len(term) > 2]
    if not terms:
        return []

    clauses = " OR ".join(["LOWER(text) LIKE ?"] * len(terms))
    params: List[Any] = [f"%{term}%" for term in terms]
    query = f"SELECT * FROM conversation_messages WHERE ({clauses})"

    if session_id:
        query += " AND session_id = ?"
        params.append(session_id)
    if exclude_session:
        query += " AND session_id != ?"
        params.append(exclude_session)

    query += " ORDER BY id DESC LIMIT ?"
    params.append(limit)

    rows = _query(query, params)
    for row in rows:
        row["entities"] = _loads(row.get("entities"), [])
    return rows


def message_count(session_id: str) -> int:
    rows = _query(
        "SELECT COUNT(*) AS n FROM conversation_messages WHERE session_id = ?",
        (session_id,),
    )
    return int(rows[0]["n"]) if rows else 0


def messages_range(session_id: str, from_id: int, to_id: int) -> List[Dict[str, Any]]:
    rows = _query(
        """
        SELECT * FROM conversation_messages
         WHERE session_id = ? AND id > ? AND id <= ?
         ORDER BY id ASC
        """,
        (session_id, from_id, to_id),
    )
    for row in rows:
        row["entities"] = _loads(row.get("entities"), [])
    return rows


# ------------------------------------------------------------------
# conversation state
# ------------------------------------------------------------------
def save_state(session_id: str, state: Dict[str, Any]) -> None:
    _execute(
        """
        INSERT INTO conversation_context (session_id, state, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(session_id) DO UPDATE SET
            state = excluded.state,
            updated_at = excluded.updated_at
        """,
        (session_id, _dumps(state), _now()),
    )


def load_state(session_id: str) -> Dict[str, Any]:
    rows = _query(
        "SELECT state FROM conversation_context WHERE session_id = ?", (session_id,)
    )
    if not rows:
        return {}
    return _loads(rows[0].get("state"), {}) or {}


# ------------------------------------------------------------------
# entities
# ------------------------------------------------------------------
def upsert_entity(
    session_id: str,
    name: str,
    type: str,
    aliases: Optional[List[str]] = None,
    context: str = "",
) -> None:
    now = _now()
    _execute(
        """
        INSERT INTO conversation_entities
            (session_id, name, type, aliases, context,
             first_mention, last_mention, mention_count)
        VALUES (?, ?, ?, ?, ?, ?, ?, 1)
        ON CONFLICT(session_id, name, type) DO UPDATE SET
            last_mention  = excluded.last_mention,
            mention_count = mention_count + 1,
            aliases       = excluded.aliases,
            context       = CASE WHEN excluded.context = '' THEN context
                                 ELSE excluded.context END
        """,
        (session_id, name, type, _dumps(aliases or []), context, now, now),
    )


def entities(session_id: str, limit: int = 30) -> List[Dict[str, Any]]:
    rows = _query(
        """
        SELECT * FROM conversation_entities
         WHERE session_id = ?
         ORDER BY last_mention DESC, mention_count DESC
         LIMIT ?
        """,
        (session_id, limit),
    )
    for row in rows:
        row["aliases"] = _loads(row.get("aliases"), [])
    return rows


def find_entity(name: str, session_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    query = "SELECT * FROM conversation_entities WHERE LOWER(name) = ?"
    params: List[Any] = [name.strip().lower()]
    if session_id:
        query += " AND session_id = ?"
        params.append(session_id)
    query += " ORDER BY last_mention DESC LIMIT 1"
    rows = _query(query, params)
    if not rows:
        return None
    rows[0]["aliases"] = _loads(rows[0].get("aliases"), [])
    return rows[0]


# ------------------------------------------------------------------
# topics
# ------------------------------------------------------------------
def upsert_topic(session_id: str, topic: str) -> None:
    now = _now()
    _execute(
        """
        INSERT INTO conversation_topics
            (session_id, topic, started_at, last_seen_at, message_count)
        VALUES (?, ?, ?, ?, 1)
        ON CONFLICT(session_id, topic) DO UPDATE SET
            last_seen_at  = excluded.last_seen_at,
            message_count = message_count + 1
        """,
        (session_id, topic, now, now),
    )


def topics(session_id: str, limit: int = 15) -> List[Dict[str, Any]]:
    return _query(
        """
        SELECT * FROM conversation_topics
         WHERE session_id = ?
         ORDER BY last_seen_at DESC
         LIMIT ?
        """,
        (session_id, limit),
    )


# ------------------------------------------------------------------
# summaries
# ------------------------------------------------------------------
def add_summary(
    session_id: str, summary: str, covers_from: int = 0, covers_to: int = 0
) -> None:
    _execute(
        """
        INSERT INTO conversation_summaries
            (session_id, summary, covers_from, covers_to, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (session_id, summary, covers_from, covers_to, _now()),
    )
    _execute(
        "UPDATE conversation_sessions SET summary = ? WHERE session_id = ?",
        (summary, session_id),
    )


def last_summary(session_id: str) -> Optional[Dict[str, Any]]:
    rows = _query(
        """
        SELECT * FROM conversation_summaries
         WHERE session_id = ?
         ORDER BY id DESC LIMIT 1
        """,
        (session_id,),
    )
    return rows[0] if rows else None


def summaries(session_id: str, limit: int = 5) -> List[Dict[str, Any]]:
    return _query(
        """
        SELECT * FROM conversation_summaries
         WHERE session_id = ?
         ORDER BY id DESC LIMIT ?
        """,
        (session_id, limit),
    )


# ------------------------------------------------------------------
# maintenance / testing helpers
# ------------------------------------------------------------------
def use_database(path: str) -> None:
    """Point the store at another database file (used by tests)."""
    global DATABASE, DATA_DIR, _READY
    with _LOCK:
        DATABASE = Path(path)
        DATA_DIR = DATABASE.parent
        _READY = False
        create_tables()


def reset() -> None:
    """Delete every conversation row. Only affects conversation.db."""
    for table in (
        "conversation_messages",
        "conversation_context",
        "conversation_entities",
        "conversation_topics",
        "conversation_summaries",
        "conversation_sessions",
    ):
        _execute(f"DELETE FROM {table}")
