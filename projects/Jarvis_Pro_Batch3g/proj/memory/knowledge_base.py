"""
==========================================
JARVIS PRO
Knowledge base
==========================================

Roadmap section 22 (knowledge acquisition) and the KNOWLEDGE stage of the
section 42 loop.

Facts JARVIS has learned - from you, from research, or from its own
experience - stored with a source, a confidence and a topic, searchable
offline, and de-duplicated so the same fact is not learned twice.

    from memory.knowledge_base import knowledge

    knowledge.learn("Krishna prefers Hinglish replies", topic="preferences",
                    source="user", confidence=0.95)
    knowledge.search("hinglish")
    knowledge.brief("preferences")

The key/value memory in ``memory/memory_manager.py`` stays for profile-style
facts; this is the larger, searchable, sourced store.
"""

from __future__ import annotations

import re
import sqlite3
import threading
import time
from typing import Any


STOP_WORDS = {
    "the", "a", "an", "is", "was", "are", "of", "and", "to", "in", "on",
    "for", "that", "this", "with", "it", "as", "be", "by", "from",
}

TRUSTED_SOURCES = {"user": 1.0, "experience": 0.8, "research": 0.7, "model": 0.5}


class KnowledgeBase:
    """Sourced, searchable long-term facts."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._ready = False

    # ---------------------------------------------------- storage

    def _path(self) -> str:
        try:
            from config import config

            return str(config.data_path() / "knowledge.db")

        except Exception:
            return "data/knowledge.db"

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._path(), timeout=10)
        connection.row_factory = sqlite3.Row

        if not self._ready:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS facts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    fact TEXT NOT NULL UNIQUE,
                    topic TEXT DEFAULT 'general',
                    source TEXT DEFAULT 'user',
                    confidence REAL DEFAULT 0.5,
                    learned REAL NOT NULL,
                    used INTEGER DEFAULT 0,
                    last_used REAL DEFAULT 0
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_facts_topic ON facts(topic)"
            )
            connection.commit()
            self._ready = True

        return connection

    def _normalise(self, text: str) -> str:
        return " ".join(str(text or "").strip().split())

    # ---------------------------------------------------- learning

    def learn(
        self,
        fact: str,
        topic: str = "general",
        source: str = "user",
        confidence: float | None = None,
    ) -> dict[str, Any]:
        """Store a fact. Repeating a known fact raises its confidence."""

        text = self._normalise(fact)

        if len(text) < 3:
            return {"ok": False, "error": "that fact is too short to store"}

        weight = (
            float(confidence)
            if confidence is not None
            else TRUSTED_SOURCES.get(str(source), 0.5)
        )
        weight = max(0.0, min(weight, 1.0))

        try:
            with self._lock:
                connection = self._connect()

                with connection:
                    existing = connection.execute(
                        "SELECT id, confidence FROM facts WHERE fact = ?", (text,)
                    ).fetchone()

                    if existing is not None:
                        raised = min(float(existing["confidence"]) + 0.1, 1.0)
                        connection.execute(
                            "UPDATE facts SET confidence = ?, source = ? "
                            "WHERE id = ?",
                            (raised, str(source), existing["id"]),
                        )
                        result = {
                            "ok": True,
                            "fact": text,
                            "confidence": round(raised, 2),
                            "new": False,
                        }

                    else:
                        connection.execute(
                            "INSERT INTO facts (fact, topic, source, confidence, "
                            "learned) VALUES (?, ?, ?, ?, ?)",
                            (
                                text,
                                str(topic or "general"),
                                str(source),
                                weight,
                                time.time(),
                            ),
                        )
                        result = {
                            "ok": True,
                            "fact": text,
                            "confidence": round(weight, 2),
                            "new": True,
                        }

                connection.close()

            return result

        except Exception as failure:
            return {"ok": False, "error": f"{type(failure).__name__}: {failure}"}

    def learn_many(
        self,
        facts: list[str],
        topic: str = "general",
        source: str = "research",
    ) -> dict[str, Any]:
        added = 0
        raised = 0

        for item in facts or []:
            outcome = self.learn(item, topic=topic, source=source)

            if outcome.get("ok"):
                if outcome.get("new"):
                    added += 1

                else:
                    raised += 1

        return {"ok": True, "added": added, "reinforced": raised}

    def forget(self, fact_or_id: Any) -> bool:
        try:
            with self._lock:
                connection = self._connect()

                with connection:
                    if isinstance(fact_or_id, int):
                        cursor = connection.execute(
                            "DELETE FROM facts WHERE id = ?", (fact_or_id,)
                        )

                    else:
                        cursor = connection.execute(
                            "DELETE FROM facts WHERE fact = ?",
                            (self._normalise(fact_or_id),),
                        )

                    removed = cursor.rowcount or 0

                connection.close()

            return removed > 0

        except Exception:
            return False

    # ---------------------------------------------------- retrieval

    def _keywords(self, text: str) -> list[str]:
        words = re.findall(r"[a-z0-9']+", str(text or "").lower())

        return [word for word in words if word not in STOP_WORDS and len(word) > 2]

    def search(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        """Keyword search, ranked by overlap and confidence."""

        keywords = self._keywords(query)

        if not keywords:
            return []

        try:
            with self._lock:
                connection = self._connect()
                rows = [
                    dict(row)
                    for row in connection.execute("SELECT * FROM facts").fetchall()
                ]
                connection.close()

        except Exception:
            return []

        scored: list[tuple[float, dict[str, Any]]] = []

        for row in rows:
            haystack = f"{row['fact']} {row['topic']}".lower()
            hits = sum(1 for word in keywords if word in haystack)

            if hits:
                score = hits / len(keywords) + float(row["confidence"]) * 0.3
                scored.append((score, row))

        scored.sort(key=lambda item: item[0], reverse=True)
        found = [row for _, row in scored[:limit]]

        self._mark_used([row["id"] for row in found])

        return found

    def _mark_used(self, ids: list[int]) -> None:
        if not ids:
            return

        try:
            with self._lock:
                connection = self._connect()

                with connection:
                    connection.executemany(
                        "UPDATE facts SET used = used + 1, last_used = ? "
                        "WHERE id = ?",
                        [(time.time(), item) for item in ids],
                    )

                connection.close()

        except Exception:
            pass

    def by_topic(self, topic: str, limit: int = 20) -> list[dict[str, Any]]:
        try:
            with self._lock:
                connection = self._connect()
                rows = connection.execute(
                    "SELECT * FROM facts WHERE topic = ? "
                    "ORDER BY confidence DESC LIMIT ?",
                    (str(topic), int(limit)),
                ).fetchall()
                connection.close()

            return [dict(row) for row in rows]

        except Exception:
            return []

    def topics(self) -> list[str]:
        try:
            with self._lock:
                connection = self._connect()
                rows = connection.execute(
                    "SELECT DISTINCT topic FROM facts ORDER BY topic"
                ).fetchall()
                connection.close()

            return [str(row["topic"]) for row in rows]

        except Exception:
            return []

    def brief(self, query: str = "", limit: int = 8) -> str:
        """Compact block of relevant knowledge for a prompt."""

        rows = self.search(query, limit=limit) if query else self.recent(limit)

        if not rows:
            return ""

        lines = ["[WHAT I HAVE LEARNED]"]

        for row in rows:
            lines.append(f"- {row['fact']} (source: {row['source']})")

        return "\n".join(lines)

    def recent(self, limit: int = 10) -> list[dict[str, Any]]:
        try:
            with self._lock:
                connection = self._connect()
                rows = connection.execute(
                    "SELECT * FROM facts ORDER BY learned DESC LIMIT ?",
                    (int(limit),),
                ).fetchall()
                connection.close()

            return [dict(row) for row in rows]

        except Exception:
            return []

    def status(self) -> dict[str, Any]:
        try:
            with self._lock:
                connection = self._connect()
                total = connection.execute(
                    "SELECT COUNT(*) AS n FROM facts"
                ).fetchone()["n"]
                sources = connection.execute(
                    "SELECT source, COUNT(*) AS n FROM facts GROUP BY source"
                ).fetchall()
                connection.close()

            return {
                "facts": int(total),
                "topics": self.topics(),
                "by_source": {str(row["source"]): int(row["n"]) for row in sources},
            }

        except Exception:
            return {"facts": 0, "topics": [], "by_source": {}}


knowledge = KnowledgeBase()
