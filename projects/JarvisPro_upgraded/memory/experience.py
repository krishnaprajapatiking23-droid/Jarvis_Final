"""
==========================================
JARVIS PRO
Experience system
==========================================

Roadmap section 40 (self-learning: experience system) and the
EXPERIENCE -> PATTERN -> KNOWLEDGE part of the section 42 loop.

Every finished task is stored as an experience: what was asked, what plan was
used, whether it worked, how long it took and what went wrong. Those records
are what ``learning/behaviour.py`` mines for patterns and what
``core/self_improvement.py`` uses to change strategy.

    from memory.experience import experience

    experience.record("open notepad", success=True, steps=1, duration=0.4)
    experience.advice("open notepad")      # what happened last time
    experience.best_strategy("open notepad")

Storage is a small SQLite file next to the other JARVIS databases, so it
survives restarts and needs no server.
"""

from __future__ import annotations

import json
import re
import sqlite3
import threading
import time
from typing import Any


STOP_WORDS = {
    "the", "a", "an", "my", "me", "i", "you", "to", "of", "and", "on", "in",
    "for", "please", "jarvis", "can", "could", "would", "just", "now",
}


class ExperienceStore:
    """Durable record of everything JARVIS has tried."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._ready = False

    # ---------------------------------------------------- storage

    def _path(self) -> str:
        try:
            from config import config

            return str(config.data_path() / "experience.db")

        except Exception:
            return "data/experience.db"

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._path(), timeout=10)
        connection.row_factory = sqlite3.Row

        if not self._ready:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS experiences (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    at REAL NOT NULL,
                    goal TEXT NOT NULL,
                    signature TEXT NOT NULL,
                    strategy TEXT DEFAULT '',
                    success INTEGER NOT NULL,
                    steps INTEGER DEFAULT 0,
                    duration REAL DEFAULT 0,
                    error TEXT DEFAULT '',
                    details TEXT DEFAULT '{}'
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_experience_signature "
                "ON experiences(signature)"
            )
            connection.commit()
            self._ready = True

        return connection

    # ---------------------------------------------------- helpers

    def signature(self, goal: str) -> str:
        """Normalised fingerprint so similar requests group together."""

        words = re.findall(r"[a-z0-9]+", str(goal or "").lower())
        kept = [word for word in words if word not in STOP_WORDS]

        return " ".join(sorted(set(kept))[:6])

    # ---------------------------------------------------- writing

    def record(
        self,
        goal: str,
        success: bool,
        steps: int = 0,
        duration: float = 0.0,
        strategy: str = "",
        error: str = "",
        **details: Any,
    ) -> dict[str, Any]:
        """Store one finished task. Never raises."""

        entry = {
            "at": time.time(),
            "goal": str(goal or "")[:400],
            "signature": self.signature(goal),
            "strategy": str(strategy or "")[:120],
            "success": 1 if success else 0,
            "steps": int(steps or 0),
            "duration": float(duration or 0.0),
            "error": str(error or "")[:400],
            "details": json.dumps(details, default=str)[:2000],
        }

        try:
            with self._lock:
                connection = self._connect()

                with connection:
                    connection.execute(
                        "INSERT INTO experiences (at, goal, signature, strategy, "
                        "success, steps, duration, error, details) "
                        "VALUES (:at, :goal, :signature, :strategy, :success, "
                        ":steps, :duration, :error, :details)",
                        entry,
                    )

                connection.close()

        except Exception:
            return {**entry, "stored": False}

        try:
            from core.event_bus import event_bus

            event_bus.publish("experience.recorded", entry)

        except Exception:
            pass

        return {**entry, "stored": True}

    # ---------------------------------------------------- reading

    def _query(self, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
        try:
            with self._lock:
                connection = self._connect()
                rows = connection.execute(sql, params).fetchall()
                connection.close()

            return [dict(row) for row in rows]

        except Exception:
            return []

    def recent(self, limit: int = 20) -> list[dict[str, Any]]:
        return self._query(
            "SELECT * FROM experiences ORDER BY at DESC LIMIT ?", (int(limit),)
        )

    def similar(self, goal: str, limit: int = 10) -> list[dict[str, Any]]:
        """Past attempts at the same kind of request."""

        fingerprint = self.signature(goal)

        if not fingerprint:
            return []

        exact = self._query(
            "SELECT * FROM experiences WHERE signature = ? "
            "ORDER BY at DESC LIMIT ?",
            (fingerprint, int(limit)),
        )

        if exact:
            return exact

        # fall back to partial word overlap
        wanted = set(fingerprint.split())
        scored: list[tuple[int, dict[str, Any]]] = []

        for row in self.recent(200):
            overlap = len(wanted & set(str(row["signature"]).split()))

            if overlap:
                scored.append((overlap, row))

        scored.sort(key=lambda item: item[0], reverse=True)

        return [row for _, row in scored[:limit]]

    def failures(self, limit: int = 20) -> list[dict[str, Any]]:
        return self._query(
            "SELECT * FROM experiences WHERE success = 0 "
            "ORDER BY at DESC LIMIT ?",
            (int(limit),),
        )

    # ---------------------------------------------------- learning views

    def stats(self, goal: str = "") -> dict[str, Any]:
        """Success rate and timing, overall or for one kind of request."""

        if goal:
            rows = self.similar(goal, limit=100)

        else:
            rows = self._query("SELECT * FROM experiences")

        if not rows:
            return {
                "attempts": 0,
                "successes": 0,
                "success_rate": 0.0,
                "average_duration": 0.0,
                "average_steps": 0.0,
            }

        successes = sum(1 for row in rows if row["success"])

        return {
            "attempts": len(rows),
            "successes": successes,
            "success_rate": round(successes / len(rows) * 100, 1),
            "average_duration": round(
                sum(float(row["duration"]) for row in rows) / len(rows), 2
            ),
            "average_steps": round(
                sum(int(row["steps"]) for row in rows) / len(rows), 2
            ),
        }

    def best_strategy(self, goal: str) -> str:
        """The strategy that worked most often for this kind of request."""

        tally: dict[str, list[int]] = {}

        for row in self.similar(goal, limit=50):
            strategy = str(row["strategy"] or "").strip()

            if not strategy:
                continue

            bucket = tally.setdefault(strategy, [0, 0])
            bucket[0] += 1

            if row["success"]:
                bucket[1] += 1

        if not tally:
            return ""

        ranked = sorted(
            tally.items(),
            key=lambda item: (item[1][1] / item[1][0], item[1][0]),
            reverse=True,
        )
        best, counts = ranked[0]

        return best if counts[1] else ""

    def advice(self, goal: str) -> str:
        """One short sentence of hindsight to put in a planning prompt."""

        rows = self.similar(goal, limit=10)

        if not rows:
            return ""

        successes = [row for row in rows if row["success"]]
        failures = [row for row in rows if not row["success"]]

        if successes and not failures:
            return (
                f"You have done this {len(successes)} time(s) before and it "
                "worked; repeat the same approach."
            )

        if failures and not successes:
            reason = str(failures[0]["error"] or "it failed").strip()

            return f"This failed before ({reason}); try a different approach."

        if successes and failures:
            strategy = self.best_strategy(goal)
            tail = f" What worked was: {strategy}." if strategy else ""

            return (
                f"Mixed history: {len(successes)} success(es), "
                f"{len(failures)} failure(s).{tail}"
            )

        return ""

    def purge(self, keep: int = 2000) -> int:
        """Keep the newest records only."""

        try:
            with self._lock:
                connection = self._connect()

                with connection:
                    cursor = connection.execute(
                        "DELETE FROM experiences WHERE id NOT IN "
                        "(SELECT id FROM experiences ORDER BY at DESC LIMIT ?)",
                        (int(keep),),
                    )
                    removed = cursor.rowcount or 0

                connection.close()

            return max(removed, 0)

        except Exception:
            return 0


experience = ExperienceStore()
