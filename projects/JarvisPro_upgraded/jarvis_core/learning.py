"""Structured self-learning: experience database + 18 behaviours (S40).

Experiences live in normalised SQLite tables (`experiences` with typed columns
plus `experience_terms` for similarity search and `strategies` for strategy
statistics) rather than one growing JSON blob, so ranking, similarity and
strategy replacement are real queries instead of full-file scans.
"""

from __future__ import annotations

import json
import math
import os
import re
import sqlite3
import threading
import time
import uuid
from typing import Any, Dict, Iterable, List, Optional, Sequence

__all__ = ["EXPERIENCE_TYPES", "ExperienceDB", "LearningEngine", "learning", "tokenize"]

EXPERIENCE_TYPES = (
    "experience",
    "success",
    "failure",
    "error",
    "correction",
    "feedback",
    "workflow",
    "command",
    "strategy",
    "negative",
)
STOPWORDS = {"the", "a", "an", "to", "of", "and", "for", "is", "in", "on", "it", "my", "me", "with", "that", "this"}
STALE_AFTER_DAYS = 120.0

SCHEMA = """
CREATE TABLE IF NOT EXISTS experiences (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    context TEXT NOT NULL,
    action TEXT NOT NULL,
    result TEXT NOT NULL DEFAULT '',
    success INTEGER NOT NULL DEFAULT 0,
    failure TEXT NOT NULL DEFAULT '',
    error TEXT NOT NULL DEFAULT '',
    correction TEXT NOT NULL DEFAULT '',
    strategy TEXT NOT NULL DEFAULT '',
    confidence REAL NOT NULL DEFAULT 0.5,
    importance REAL NOT NULL DEFAULT 0.4,
    uses INTEGER NOT NULL DEFAULT 0,
    verified INTEGER NOT NULL DEFAULT 0,
    retired INTEGER NOT NULL DEFAULT 0,
    trace_id TEXT NOT NULL DEFAULT '',
    meta TEXT NOT NULL DEFAULT '{}',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS experience_terms (
    experience_id TEXT NOT NULL,
    term TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS strategies (
    name TEXT PRIMARY KEY,
    domain TEXT NOT NULL DEFAULT 'general',
    successes INTEGER NOT NULL DEFAULT 0,
    failures INTEGER NOT NULL DEFAULT 0,
    retired INTEGER NOT NULL DEFAULT 0,
    replaced_by TEXT NOT NULL DEFAULT '',
    updated_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS experiences_type ON experiences(type, success);
CREATE INDEX IF NOT EXISTS experience_terms_term ON experience_terms(term);
"""


def tokenize(text: str) -> List[str]:
    words = re.findall(r"[a-z0-9]+", str(text or "").lower())
    return [word for word in words if word not in STOPWORDS and len(word) > 2]


class ExperienceDB:
    """Storage layer for experiences (Experience Database)."""

    def __init__(self, path: str = "data/experience.db") -> None:
        self.path = path
        self._local = threading.local()
        self.lock = threading.RLock()
        self._ready = False

    def connect(self) -> sqlite3.Connection:
        connection = getattr(self._local, "connection", None)
        if connection is not None:
            return connection
        directory = os.path.dirname(self.path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=15.0)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA busy_timeout=15000")
        except sqlite3.DatabaseError:
            pass
        self._local.connection = connection
        if not self._ready:
            with self.lock:
                connection.executescript(SCHEMA)
                connection.commit()
                self._ready = True
        return connection


class LearningEngine:
    """Section 40 behaviours implemented on top of the experience database."""

    def __init__(self, db: Optional[ExperienceDB] = None) -> None:
        self.db = db or ExperienceDB()

    # --------------------------------------------------------------- writing
    def record(
        self,
        context: str,
        action: str,
        result: str = "",
        success: bool = True,
        kind: str = "experience",
        failure: str = "",
        error: str = "",
        correction: str = "",
        strategy: str = "",
        confidence: float = 0.5,
        importance: float = 0.4,
        trace_id: str = "",
        verified: bool = False,
        **meta: Any,
    ) -> Dict[str, Any]:
        if kind not in EXPERIENCE_TYPES:
            raise ValueError("kind must be one of %s" % (EXPERIENCE_TYPES,))
        if not str(action).strip():
            raise ValueError("an experience needs an action")
        now = time.time()
        experience_id = uuid.uuid4().hex[:12]
        connection = self.db.connect()
        with self.db.lock:
            connection.execute(
                "INSERT INTO experiences (id, type, context, action, result, success, failure,"
                " error, correction, strategy, confidence, importance, uses, verified, retired,"
                " trace_id, meta, created_at, updated_at)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,0,?,0,?,?,?,?)",
                (
                    experience_id,
                    kind,
                    str(context),
                    str(action),
                    str(result),
                    1 if success else 0,
                    str(failure),
                    str(error),
                    str(correction),
                    str(strategy),
                    float(confidence),
                    float(importance),
                    1 if verified else 0,
                    str(trace_id),
                    json.dumps(meta, default=str),
                    now,
                    now,
                ),
            )
            for term in set(tokenize(str(context) + " " + str(action) + " " + str(result))):
                connection.execute(
                    "INSERT INTO experience_terms (experience_id, term) VALUES (?, ?)",
                    (experience_id, term),
                )
            if strategy:
                self._touch_strategy(connection, strategy, success)
            connection.commit()
        return self.get(experience_id)

    def _touch_strategy(self, connection: sqlite3.Connection, name: str, success: bool) -> None:
        now = time.time()
        win = 1 if success else 0
        loss = 0 if success else 1
        connection.execute(
            "INSERT INTO strategies (name, successes, failures, updated_at) VALUES (?, ?, ?, ?)"
            " ON CONFLICT(name) DO UPDATE SET successes = successes + ?, failures = failures + ?,"
            " updated_at = ?",
            (str(name), win, loss, now, win, loss, now),
        )

    # ------------------------------------------------ named learning methods
    def learn_success(self, context: str, action: str, result: str = "", **kw: Any) -> Dict[str, Any]:
        return self.record(context, action, result, True, "success", confidence=0.7, **kw)

    def learn_failure(self, context: str, action: str, failure: str, **kw: Any) -> Dict[str, Any]:
        return self.record(context, action, "", False, "failure", failure=failure, confidence=0.6, **kw)

    def learn_error(self, context: str, action: str, error: str, **kw: Any) -> Dict[str, Any]:
        return self.record(context, action, "", False, "error", error=error, confidence=0.6, **kw)

    def learn_correction(self, context: str, wrong_action: str, correction: str, **kw: Any) -> Dict[str, Any]:
        return self.record(
            context, wrong_action, "", False, "correction",
            correction=correction, confidence=0.5, importance=0.6, **kw,
        )

    def save_correction(self, experience_id: str, worked: bool = True) -> Dict[str, Any]:
        """Save Successful Correction - promoted only after verification (S20)."""
        record = self.get(experience_id)
        if record["type"] != "correction":
            raise ValueError("only correction experiences can be promoted")
        if not worked:
            return self._update(experience_id, confidence=max(0.1, record["confidence"] - 0.2), verified=0)
        return self._update(
            experience_id,
            verified=1,
            confidence=min(1.0, record["confidence"] + 0.3),
            importance=min(1.0, record["importance"] + 0.2),
        )

    def learn_feedback(self, context: str, action: str, rating: int, comment: str = "") -> Dict[str, Any]:
        rating = max(-1, min(1, int(rating)))
        return self.record(
            context, action, comment, rating >= 0, "feedback",
            confidence=0.9, importance=0.7, rating=rating,
        )

    def learn_workflow(self, name: str, steps: Sequence[str], success: bool = True) -> Dict[str, Any]:
        joined = " -> ".join(str(step) for step in steps)
        return self.record("workflow:" + str(name), joined, "", success, "workflow", strategy=name, confidence=0.6)

    def learn_command(self, command: str, resolved_to: str, success: bool = True) -> Dict[str, Any]:
        return self.record("command:" + str(command), resolved_to, "", success, "command", confidence=0.6)

    def learn_strategy(self, name: str, domain: str, success: bool, detail: str = "") -> Dict[str, Any]:
        connection = self.db.connect()
        with self.db.lock:
            self._touch_strategy(connection, name, success)
            connection.execute("UPDATE strategies SET domain = ? WHERE name = ?", (str(domain), str(name)))
            connection.commit()
        return self.record("strategy:" + str(domain), name, detail, success, "strategy", strategy=name)

    def learn_negative(self, context: str, action: str, why: str) -> Dict[str, Any]:
        return self.record(context, action, "", False, "negative", failure=why, confidence=0.8, importance=0.8)

    def avoid(self, context: str, action: str) -> Optional[Dict[str, Any]]:
        connection = self.db.connect()
        with self.db.lock:
            row = connection.execute(
                "SELECT * FROM experiences WHERE type = 'negative' AND retired = 0 AND action = ?"
                " AND (context = ? OR context = '') ORDER BY importance DESC LIMIT 1",
                (str(action), str(context)),
            ).fetchone()
        return None if row is None else self._row(row)

    # ------------------------------------------------------------------ read
    def get(self, experience_id: str) -> Dict[str, Any]:
        connection = self.db.connect()
        with self.db.lock:
            row = connection.execute(
                "SELECT * FROM experiences WHERE id = ?", (str(experience_id),)
            ).fetchone()
        if row is None:
            raise KeyError("experience %s not found" % experience_id)
        return self._row(row)

    @staticmethod
    def _row(row: sqlite3.Row) -> Dict[str, Any]:
        try:
            meta = json.loads(row["meta"] or "{}")
        except ValueError:
            meta = {}
        return {
            "id": row["id"],
            "type": row["type"],
            "context": row["context"],
            "action": row["action"],
            "result": row["result"],
            "success": bool(row["success"]),
            "failure": row["failure"],
            "error": row["error"],
            "correction": row["correction"],
            "strategy": row["strategy"],
            "confidence": float(row["confidence"]),
            "importance": float(row["importance"]),
            "uses": int(row["uses"]),
            "verified": bool(row["verified"]),
            "retired": bool(row["retired"]),
            "trace_id": row["trace_id"],
            "meta": meta,
            "created_at": float(row["created_at"]),
            "updated_at": float(row["updated_at"]),
        }

    def _update(self, experience_id: str, **fields: Any) -> Dict[str, Any]:
        if not fields:
            return self.get(experience_id)
        columns = ", ".join(key + " = ?" for key in fields)
        connection = self.db.connect()
        with self.db.lock:
            connection.execute(
                "UPDATE experiences SET " + columns + ", updated_at = ? WHERE id = ?",
                tuple(fields.values()) + (time.time(), str(experience_id)),
            )
            connection.commit()
        return self.get(experience_id)

    def count(self, kind: str = "") -> int:
        connection = self.db.connect()
        query = "SELECT COUNT(*) AS n FROM experiences"
        params: List[Any] = []
        if kind:
            query += " WHERE type = ?"
            params.append(kind)
        with self.db.lock:
            return int(connection.execute(query, tuple(params)).fetchone()["n"])

    # ------------------------------------------------ similarity and ranking
    def similar(self, text: str, limit: int = 5, kind: str = "") -> List[Dict[str, Any]]:
        terms = set(tokenize(text))
        if not terms:
            return []
        placeholders = ",".join("?" for _ in terms)
        query = (
            "SELECT e.*, COUNT(t.term) AS overlap FROM experience_terms t"
            " JOIN experiences e ON e.id = t.experience_id"
            " WHERE t.term IN (" + placeholders + ") AND e.retired = 0"
        )
        params: List[Any] = list(terms)
        if kind:
            query += " AND e.type = ?"
            params.append(kind)
        query += " GROUP BY e.id ORDER BY overlap DESC LIMIT ?"
        params.append(int(limit) * 3)
        connection = self.db.connect()
        with self.db.lock:
            rows = list(connection.execute(query, tuple(params)))
        scored: List[Dict[str, Any]] = []
        for row in rows:
            record = self._row(row)
            own = set(tokenize(record["context"] + " " + record["action"] + " " + record["result"]))
            union = len(terms | own) or 1
            record["similarity"] = round(int(row["overlap"]) / union, 4)
            scored.append(record)
        return self.rank(scored)[: int(limit)]

    def rank(self, records: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
        now = time.time()
        ranked: List[Dict[str, Any]] = []
        for record in records:
            age_days = max(0.0, (now - record["created_at"]) / 86400.0)
            recency = math.exp(-age_days / 45.0)
            score = (
                record.get("similarity", 0.5)
                * (0.3 + record["confidence"])
                * (0.5 + record["importance"])
                * (0.4 + 0.6 * recency)
                * (1.25 if record["verified"] else 1.0)
            )
            record["rank_score"] = round(score, 5)
            ranked.append(record)
        return sorted(ranked, key=lambda item: item["rank_score"], reverse=True)

    def reuse(self, experience_id: str) -> Dict[str, Any]:
        record = self.get(experience_id)
        return self._update(experience_id, uses=record["uses"] + 1)

    # ------------------------------------------------- planning and strategy
    def adapt_plan(self, goal: str, steps: Sequence[str]) -> Dict[str, Any]:
        """Adaptive Planning: order/annotate steps from recorded evidence."""
        plan: List[Dict[str, Any]] = []
        for step in steps:
            warning = self.avoid(goal, str(step))
            history = self.similar(str(goal) + " " + str(step), limit=3)
            wins = [item for item in history if item["success"]]
            losses = [item for item in history if not item["success"]]
            plan.append(
                {
                    "step": str(step),
                    "skip": bool(warning),
                    "reason": warning["failure"] if warning else "",
                    "prior_successes": len(wins),
                    "prior_failures": len(losses),
                    "confidence": round(
                        0.5 + 0.1 * len(wins) - 0.15 * len(losses) - (0.4 if warning else 0.0), 3
                    ),
                }
            )
        kept = [item for item in plan if not item["skip"]]
        kept.sort(key=lambda item: item["confidence"], reverse=True)
        return {
            "goal": goal,
            "steps": plan,
            "ordered": [item["step"] for item in kept],
            "skipped": [item["step"] for item in plan if item["skip"]],
            "evidence": "ordered by recorded success/failure of each step",
        }

    def strategy_stats(self, name: str = "") -> List[Dict[str, Any]]:
        connection = self.db.connect()
        query = "SELECT * FROM strategies"
        params: List[Any] = []
        if name:
            query += " WHERE name = ?"
            params.append(name)
        with self.db.lock:
            rows = list(connection.execute(query, tuple(params)))
        output: List[Dict[str, Any]] = []
        for row in rows:
            total = int(row["successes"]) + int(row["failures"])
            output.append(
                {
                    "name": row["name"],
                    "domain": row["domain"],
                    "successes": int(row["successes"]),
                    "failures": int(row["failures"]),
                    "success_rate": round(int(row["successes"]) / total, 3) if total else 0.0,
                    "samples": total,
                    "retired": bool(row["retired"]),
                    "replaced_by": row["replaced_by"],
                }
            )
        return output

    def replace_strategy(self, old: str, new: str, min_samples: int = 3) -> Dict[str, Any]:
        stats = {item["name"]: item for item in self.strategy_stats()}
        before = stats.get(old)
        after = stats.get(new)
        if before is None or after is None:
            return {"replaced": False, "reason": "both strategies must have recorded results"}
        if after["samples"] < int(min_samples):
            return {
                "replaced": False,
                "reason": "%s has only %d samples; need %d" % (new, after["samples"], min_samples),
            }
        if after["success_rate"] <= before["success_rate"]:
            return {
                "replaced": False,
                "reason": "%s (%.2f) does not beat %s (%.2f)"
                % (new, after["success_rate"], old, before["success_rate"]),
            }
        connection = self.db.connect()
        with self.db.lock:
            connection.execute(
                "UPDATE strategies SET retired = 1, replaced_by = ?, updated_at = ? WHERE name = ?",
                (str(new), time.time(), str(old)),
            )
            connection.commit()
        return {
            "replaced": True,
            "old": old,
            "new": new,
            "reason": "%s succeeds %.2f vs %.2f" % (new, after["success_rate"], before["success_rate"]),
        }

    def best_strategy(self, domain: str = "") -> Optional[Dict[str, Any]]:
        items = [
            item
            for item in self.strategy_stats()
            if not item["retired"] and (not domain or item["domain"] == domain)
        ]
        if not items:
            return None
        return max(items, key=lambda item: (item["success_rate"], item["samples"]))

    # ----------------------------------------- importance and outdated check
    def memory_importance(self, key: str) -> Dict[str, Any]:
        matches = self.similar(key, limit=10)
        if not matches:
            return {"key": key, "importance": 0.3, "evidence": 0, "reason": "no related experience"}
        uses = sum(item["uses"] for item in matches)
        wins = sum(1 for item in matches if item["success"])
        score = min(1.0, 0.25 + 0.05 * uses + 0.06 * wins)
        return {
            "key": key,
            "importance": round(score, 3),
            "evidence": len(matches),
            "reason": "%d successful and %d reused related experiences" % (wins, uses),
        }

    def outdated(self, stale_days: float = STALE_AFTER_DAYS) -> List[Dict[str, Any]]:
        cutoff = time.time() - float(stale_days) * 86400.0
        connection = self.db.connect()
        with self.db.lock:
            stale_rows = list(
                connection.execute(
                    "SELECT * FROM experiences WHERE retired = 0 AND updated_at < ? AND uses = 0",
                    (cutoff,),
                )
            )
            strategy_rows = list(
                connection.execute("SELECT * FROM experiences WHERE retired = 0 AND strategy != ''")
            )
        retired = {item["name"] for item in self.strategy_stats() if item["retired"]}
        output: List[Dict[str, Any]] = []
        for row in stale_rows:
            record = self._row(row)
            record["reason"] = "never reused and older than the freshness window"
            output.append(record)
        for row in strategy_rows:
            record = self._row(row)
            if record["strategy"] in retired:
                record["reason"] = "uses retired strategy '%s'" % record["strategy"]
                output.append(record)
        return output

    def retire(self, experience_id: str, reason: str = "outdated") -> Dict[str, Any]:
        return self._update(experience_id, retired=1, failure=str(reason))

    # ---------------------------------------------------------------- report
    def stats(self) -> Dict[str, Any]:
        connection = self.db.connect()
        with self.db.lock:
            rows = list(
                connection.execute(
                    "SELECT type, COUNT(*) AS n, SUM(success) AS ok FROM experiences GROUP BY type"
                )
            )
            total = int(connection.execute("SELECT COUNT(*) AS n FROM experiences").fetchone()["n"])
            verified = int(
                connection.execute(
                    "SELECT COUNT(*) AS n FROM experiences WHERE verified = 1"
                ).fetchone()["n"]
            )
        by_type = {row["type"]: {"count": int(row["n"]), "successes": int(row["ok"] or 0)} for row in rows}
        return {
            "total": total,
            "verified": verified,
            "by_type": by_type,
            "strategies": self.strategy_stats(),
            "outdated": len(self.outdated()),
        }

    def clear(self) -> None:
        connection = self.db.connect()
        with self.db.lock:
            for table in ("experiences", "experience_terms", "strategies"):
                connection.execute("DELETE FROM " + table)
            connection.commit()


learning = LearningEngine()
