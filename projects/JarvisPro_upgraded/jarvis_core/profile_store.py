"""Section 5 + 6 - personal profile and personality.

* Profile attributes are versioned: every write snapshots the previous value,
  so ``history()`` and ``revert()`` are real operations.
* ``correct()`` is the explicit user-correction path. A correction always wins
  over inference and is recorded as evidence with the highest reliability.
* ``observe()`` is the automatic-learning path. It requires repeated evidence
  (``MIN_EVIDENCE``) before a value is promoted, which is what stops one
  accidental action from becoming a permanent preference.
* Goals form a hierarchy (long/medium/short term) with priority, dependencies
  and constraints; ``goal_tree()`` and ``next_goal()`` are inspectable.
* Constraints and permissions are enforceable structures the policy layer can
  consult, not free text.
* Expertise is estimated only from interaction evidence.
* :class:`Personality` keeps a stable core and only lets the conversation layer
  vary presentation, which is how consistency across GUI/voice/Android/agents
  is guaranteed.

Storage: ``data/profile.db``.
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

_DEF_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")

# evidence reliability by source - user corrections dominate inference
SOURCE_RELIABILITY = {
    "user_correction": 1.0,
    "user_statement": 0.9,
    "conversation_signal": 0.45,  # profile signal detected from self-referential conversation
    "observation": 0.5,
    "inference": 0.35,
}

MIN_EVIDENCE = 3           # repeated observations required before auto-learning
MIN_EVIDENCE_CONFIDENCE = 0.55

HORIZONS = ("long_term", "medium_term", "short_term")

EXPERTISE_LEVELS = ((0.0, "novice"), (0.35, "intermediate"), (0.6, "advanced"), (0.85, "expert"))


class ConstraintViolation(Exception):
    """Raised when an action breaks a user constraint."""


def _utc() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())


def _utc_in(seconds: float) -> str:
    """Timestamp ``seconds`` from now, in the same UTC format as :func:`_utc`."""
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(time.time() + seconds))


def _expired(stamp: Optional[str], now: Optional[str] = None) -> bool:
    """True when ``stamp`` is a timestamp already in the past.

    Section 8 requires temporary preferences to expire while permanent ones
    persist. Timestamps are fixed-width UTC strings, so a plain string
    comparison is a correct chronological comparison and stays timezone-safe.
    """
    if not stamp:
        return False
    return stamp <= (now or _utc())


@dataclass
class Attribute:
    key: str
    value: Any
    confidence: float
    source: str
    version: int
    updated_at: str
    evidence_count: int = 0
    expires_at: Optional[str] = None

    @property
    def temporary(self) -> bool:
        """True for a preference that is set to expire."""
        return bool(self.expires_at)

    def to_dict(self) -> Dict[str, Any]:
        return dict(self.__dict__)


class ProfileStore:
    def __init__(self, db_path: Optional[str] = None, subject: str = "owner") -> None:
        os.makedirs(_DEF_DIR, exist_ok=True)
        self.db_path = db_path or os.path.join(_DEF_DIR, "profile.db")
        self.subject = subject
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_db()
        self._migrate()

    def _init_db(self) -> None:
        with self._lock:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS attributes (
                    subject TEXT, key TEXT, value TEXT, confidence REAL, source TEXT,
                    version INTEGER, updated_at TEXT, evidence_count INTEGER DEFAULT 0,
                    PRIMARY KEY (subject, key)
                );
                CREATE TABLE IF NOT EXISTS attribute_versions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    subject TEXT, key TEXT, value TEXT, confidence REAL, source TEXT,
                    version INTEGER, reason TEXT, actor TEXT, created_at TEXT
                );
                CREATE TABLE IF NOT EXISTS evidence (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    subject TEXT, key TEXT, value TEXT, source TEXT, weight REAL,
                    detail TEXT, created_at TEXT
                );
                CREATE TABLE IF NOT EXISTS goals (
                    goal_id TEXT PRIMARY KEY, subject TEXT, title TEXT, horizon TEXT,
                    priority INTEGER, parent TEXT, depends_on TEXT, constraints TEXT,
                    status TEXT, progress REAL, created_at TEXT, updated_at TEXT
                );
                CREATE TABLE IF NOT EXISTS constraints (
                    name TEXT PRIMARY KEY, subject TEXT, kind TEXT, spec TEXT, reason TEXT,
                    created_at TEXT
                );
                CREATE TABLE IF NOT EXISTS user_permissions (
                    scope TEXT PRIMARY KEY, subject TEXT, allowed INTEGER, reason TEXT,
                    created_at TEXT
                );
                CREATE TABLE IF NOT EXISTS expertise (
                    topic TEXT PRIMARY KEY, subject TEXT, score REAL, samples INTEGER,
                    successes INTEGER, updated_at TEXT
                );
                """
            )
            self._conn.commit()

    # ---------------- attributes / versioning ----------------
    def _migrate(self) -> None:
        """Additive schema migration (Section 32).

        Older profile.db files have no ``expires_at`` column. Adding it with
        a default of NULL keeps every existing attribute permanent, which is
        the correct interpretation of a preference stored before temporary
        preferences existed.
        """
        with self._lock:
            columns = {r["name"] for r in
                       self._conn.execute("PRAGMA table_info(attributes)")}
            if "expires_at" not in columns:
                self._conn.execute("ALTER TABLE attributes ADD COLUMN expires_at TEXT")
                self._conn.commit()

    def purge_expired(self) -> int:
        """Delete attributes whose expiry has passed. Returns the count.

        Each purge is recorded in ``attribute_versions`` so that an expired
        temporary preference remains visible in history().
        """
        now = _utc()
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM attributes WHERE subject=? AND expires_at IS NOT NULL"
                " AND expires_at<=?", (self.subject, now)).fetchall()
            for row in rows:
                self._conn.execute(
                    "INSERT INTO attribute_versions(subject, key, value, confidence,"
                    " source, version, reason, actor, created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                    (self.subject, row["key"], row["value"], row["confidence"],
                     row["source"], row["version"], "expired", "system", now),
                )
                self._conn.execute("DELETE FROM attributes WHERE subject=? AND key=?",
                                   (self.subject, row["key"]))
            self._conn.commit()
            return len(rows)

    def _load(self, key: str) -> Optional[Attribute]:
        row = self._conn.execute("SELECT * FROM attributes WHERE subject=? AND key=?",
                                 (self.subject, key)).fetchone()
        if row is None:
            return None
        expires_at = row["expires_at"] if "expires_at" in row.keys() else None
        # An expired temporary preference is treated as absent. It is not
        # deleted here: purge_expired() does that, so history stays readable.
        if _expired(expires_at):
            return None
        return Attribute(key=row["key"], value=json.loads(row["value"]),
                         confidence=row["confidence"], source=row["source"],
                         version=row["version"], updated_at=row["updated_at"],
                         evidence_count=row["evidence_count"],
                         expires_at=expires_at)

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            attr = self._load(key)
        return default if attr is None else attr.value

    def attribute(self, key: str) -> Optional[Attribute]:
        with self._lock:
            return self._load(key)

    def _write(self, key: str, value: Any, confidence: float, source: str, reason: str,
               actor: str, evidence_count: int = 0,
               expires_at: Optional[str] = None) -> Attribute:
        with self._lock:
            current = self._load(key)
            if current is not None:
                self._conn.execute(
                    "INSERT INTO attribute_versions(subject, key, value, confidence, source,"
                    " version, reason, actor, created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                    (self.subject, key, json.dumps(current.value), current.confidence,
                     current.source, current.version, f"before:{reason}", actor, _utc()),
                )
            version = (current.version + 1) if current else 1
            self._conn.execute(
                "INSERT INTO attributes(subject, key, value, confidence, source, version,"
                " updated_at, evidence_count, expires_at) VALUES(?,?,?,?,?,?,?,?,?)"
                " ON CONFLICT(subject, key) DO UPDATE SET value=excluded.value,"
                " confidence=excluded.confidence, source=excluded.source,"
                " version=excluded.version, updated_at=excluded.updated_at,"
                " evidence_count=excluded.evidence_count,"
                " expires_at=excluded.expires_at",
                (self.subject, key, json.dumps(value), float(confidence), source, version,
                 _utc(), evidence_count, expires_at),
            )
            self._conn.commit()
            return self._load(key)  # type: ignore[return-value]

    def set(self, key: str, value: Any, *, confidence: float = 0.9,
            source: str = "user_statement", reason: str = "set", actor: str = "owner",
            ttl_seconds: Optional[float] = None) -> Attribute:
        """Store a profile attribute.

        ``ttl_seconds`` makes it a *temporary* preference (Section 8): the
        value is returned normally until it expires and is treated as absent
        afterwards. Omitting it stores a permanent preference.
        """
        if not key or not isinstance(key, str):
            raise ValueError("attribute key must be a non-empty string")
        if source not in SOURCE_RELIABILITY:
            raise ValueError(f"unknown source {source!r}")
        expires_at = None
        if ttl_seconds is not None:
            if ttl_seconds <= 0:
                raise ValueError("ttl_seconds must be positive")
            expires_at = _utc_in(ttl_seconds)
        return self._write(key, value, confidence, source, reason, actor,
                           expires_at=expires_at)

    def set_temporary(self, key: str, value: Any, ttl_seconds: float, **kwargs: Any) -> Attribute:
        """Convenience wrapper: a preference that expires after ``ttl_seconds``."""
        return self.set(key, value, ttl_seconds=ttl_seconds, **kwargs)

    def make_permanent(self, key: str) -> Optional[Attribute]:
        """Promote a temporary preference to a permanent one."""
        with self._lock:
            current = self._load(key)
        if current is None:
            return None
        return self._write(current.key, current.value, current.confidence,
                           current.source, "made permanent", "owner",
                           current.evidence_count, expires_at=None)

    def correct(self, key: str, value: Any, *, actor: str = "owner",
                note: str = "") -> Attribute:
        """Explicit user correction: always wins, always versioned."""
        with self._lock:
            self._conn.execute(
                "INSERT INTO evidence(subject, key, value, source, weight, detail, created_at)"
                " VALUES(?,?,?,?,?,?,?)",
                (self.subject, key, json.dumps(value), "user_correction", 1.0,
                 note or "explicit correction", _utc()),
            )
            self._conn.commit()
        return self._write(key, value, 0.99, "user_correction", "user correction", actor)

    def history(self, key: str) -> List[Dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM attribute_versions WHERE subject=? AND key=? ORDER BY id",
                (self.subject, key)).fetchall()
        return [{**dict(row), "value": json.loads(row["value"])} for row in rows]

    def revert(self, key: str, version: int, actor: str = "owner") -> Attribute:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM attribute_versions WHERE subject=? AND key=? AND version=?"
                " ORDER BY id LIMIT 1", (self.subject, key, version)).fetchone()
        if row is None:
            raise KeyError(f"{key} has no version {version}")
        return self._write(key, json.loads(row["value"]), row["confidence"], row["source"],
                           f"revert to v{version}", actor)

    # ---------------- automatic learning ----------------
    def observe(self, key: str, value: Any, *, source: str = "observation",
                detail: str = "") -> Dict[str, Any]:
        """Record one piece of evidence; promote only when it is repeated.

        Returns a dict describing whether the profile changed and why, so the
        behaviour is inspectable instead of magical.
        """
        if source not in SOURCE_RELIABILITY:
            raise ValueError(f"unknown source {source!r}")
        weight = SOURCE_RELIABILITY[source]
        with self._lock:
            self._conn.execute(
                "INSERT INTO evidence(subject, key, value, source, weight, detail, created_at)"
                " VALUES(?,?,?,?,?,?,?)",
                (self.subject, key, json.dumps(value), source, weight, detail, _utc()),
            )
            self._conn.commit()
            rows = self._conn.execute(
                "SELECT value, source, weight FROM evidence WHERE subject=? AND key=?",
                (self.subject, key)).fetchall()

        same = [r for r in rows if json.loads(r["value"]) == value]
        total_weight = sum(r["weight"] for r in same)
        # calibrated so MIN_EVIDENCE consistent observations (weight 0.5 each)
        # clear MIN_EVIDENCE_CONFIDENCE, while one or two do not.
        confidence = round(min(0.95, total_weight / (total_weight + 1.0)), 4)
        current = self.attribute(key)

        if current is not None and current.source == "user_correction":
            return {"promoted": False, "reason": "a user correction outranks observations",
                    "evidence": len(same), "confidence": confidence}
        if len(same) < MIN_EVIDENCE or confidence < MIN_EVIDENCE_CONFIDENCE:
            return {"promoted": False,
                    "reason": f"insufficient evidence: {len(same)}/{MIN_EVIDENCE} samples,"
                              f" confidence {confidence}",
                    "evidence": len(same), "confidence": confidence}
        if current is not None and current.value == value:
            self._write(key, value, confidence, source, "evidence reinforced", "system", len(same))
            return {"promoted": False, "reason": "value already learned; confidence reinforced",
                    "evidence": len(same), "confidence": confidence}
        self._write(key, value, confidence, source, "automatic profile learning", "system",
                    len(same))
        return {"promoted": True, "reason": f"{len(same)} consistent observations",
                "evidence": len(same), "confidence": confidence}

    def evidence_for(self, key: str) -> List[Dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM evidence WHERE subject=? AND key=? ORDER BY id",
                (self.subject, key)).fetchall()
        return [{**dict(row), "value": json.loads(row["value"])} for row in rows]

    # ---------------- goals ----------------
    def add_goal(self, title: str, horizon: str = "short_term", *, priority: int = 3,
                 parent: Optional[str] = None, depends_on: Sequence[str] = (),
                 constraints: Sequence[str] = ()) -> str:
        if horizon not in HORIZONS:
            raise ValueError(f"horizon must be one of {HORIZONS}")
        if not 1 <= int(priority) <= 5:
            raise ValueError("priority must be 1..5 (1 = highest)")
        goal_id = "G-" + uuid.uuid4().hex[:8]
        with self._lock:
            if parent is not None:
                if self._conn.execute("SELECT 1 FROM goals WHERE goal_id=?", (parent,)).fetchone() is None:
                    raise KeyError(f"unknown parent goal {parent}")
            for dep in depends_on:
                if self._conn.execute("SELECT 1 FROM goals WHERE goal_id=?", (dep,)).fetchone() is None:
                    raise KeyError(f"unknown dependency {dep}")
            self._conn.execute(
                "INSERT INTO goals(goal_id, subject, title, horizon, priority, parent, depends_on,"
                " constraints, status, progress, created_at, updated_at)"
                " VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (goal_id, self.subject, title, horizon, int(priority), parent,
                 json.dumps(list(depends_on)), json.dumps(list(constraints)), "open", 0.0,
                 _utc(), _utc()),
            )
            self._conn.commit()
        return goal_id

    def _goal_row(self, goal_id: str) -> Dict[str, Any]:
        row = self._conn.execute("SELECT * FROM goals WHERE goal_id=?", (goal_id,)).fetchone()
        if row is None:
            raise KeyError(f"unknown goal {goal_id}")
        item = dict(row)
        item["depends_on"] = json.loads(item["depends_on"] or "[]")
        item["constraints"] = json.loads(item["constraints"] or "[]")
        return item

    def goal(self, goal_id: str) -> Dict[str, Any]:
        with self._lock:
            return self._goal_row(goal_id)

    def update_goal(self, goal_id: str, *, progress: Optional[float] = None,
                    status: Optional[str] = None) -> Dict[str, Any]:
        with self._lock:
            item = self._goal_row(goal_id)
            if progress is not None:
                if not 0.0 <= progress <= 1.0:
                    raise ValueError("progress must be 0..1")
                item["progress"] = float(progress)
                if progress >= 1.0 and status is None:
                    status = "done"
            if status is not None:
                if status not in ("open", "blocked", "done", "abandoned"):
                    raise ValueError(f"invalid goal status {status!r}")
                item["status"] = status
            self._conn.execute("UPDATE goals SET progress=?, status=?, updated_at=? WHERE goal_id=?",
                               (item["progress"], item["status"], _utc(), goal_id))
            self._conn.commit()
            return self._goal_row(goal_id)

    def goal_tree(self) -> List[Dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute("SELECT * FROM goals WHERE subject=?",
                                      (self.subject,)).fetchall()
        items = {}
        for row in rows:
            item = dict(row)
            item["depends_on"] = json.loads(item["depends_on"] or "[]")
            item["constraints"] = json.loads(item["constraints"] or "[]")
            item["children"] = []
            items[item["goal_id"]] = item
        roots = []
        for item in items.values():
            parent = item["parent"]
            if parent and parent in items:
                items[parent]["children"].append(item)
            else:
                roots.append(item)
        order = {h: i for i, h in enumerate(HORIZONS)}
        roots.sort(key=lambda g: (order.get(g["horizon"], 9), g["priority"]))
        for item in items.values():
            item["children"].sort(key=lambda g: g["priority"])
        return roots

    def next_goal(self) -> Optional[Dict[str, Any]]:
        """Highest-priority open goal whose dependencies are already done."""
        with self._lock:
            rows = self._conn.execute("SELECT * FROM goals WHERE subject=? AND status='open'",
                                      (self.subject,)).fetchall()
            done = {r["goal_id"] for r in self._conn.execute(
                "SELECT goal_id FROM goals WHERE status='done'").fetchall()}
        with self._lock:
            open_parents = {r["parent"] for r in self._conn.execute(
                "SELECT parent FROM goals WHERE status='open' AND parent IS NOT NULL").fetchall()}
        ready = []
        for row in rows:
            deps = json.loads(row["depends_on"] or "[]")
            if row["goal_id"] in open_parents:
                continue  # a goal with open sub-goals is a container, not the next action
            if all(dep in done for dep in deps):
                ready.append(dict(row))
        if not ready:
            return None
        order = {h: i for i, h in enumerate(HORIZONS)}
        # most actionable first: nearest horizon, then priority
        ready.sort(key=lambda g: (-order.get(g["horizon"], 9), g["priority"]))
        item = ready[0]
        item["depends_on"] = json.loads(item["depends_on"] or "[]")
        item["constraints"] = json.loads(item["constraints"] or "[]")
        return item

    # ---------------- constraints ----------------
    def add_constraint(self, name: str, kind: str, spec: Dict[str, Any], reason: str = "") -> None:
        if kind not in ("forbid_scope", "quiet_hours", "budget", "require_approval"):
            raise ValueError(f"unsupported constraint kind {kind!r}")
        with self._lock:
            self._conn.execute(
                "INSERT INTO constraints(name, subject, kind, spec, reason, created_at)"
                " VALUES(?,?,?,?,?,?) ON CONFLICT(name) DO UPDATE SET kind=excluded.kind,"
                " spec=excluded.spec, reason=excluded.reason",
                (name, self.subject, kind, json.dumps(spec), reason, _utc()),
            )
            self._conn.commit()

    def constraints(self) -> List[Dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute("SELECT * FROM constraints WHERE subject=?",
                                      (self.subject,)).fetchall()
        return [{**dict(row), "spec": json.loads(row["spec"])} for row in rows]

    def check_constraints(self, scope: str, when: Optional[time.struct_time] = None) -> Dict[str, Any]:
        """Evaluate an action scope against the user's constraints."""
        now = when or time.localtime()
        violations: List[Dict[str, Any]] = []
        approvals: List[str] = []
        for constraint in self.constraints():
            spec = constraint["spec"]
            if constraint["kind"] == "forbid_scope":
                for prefix in spec.get("scopes", []):
                    if scope == prefix or scope.startswith(prefix):
                        violations.append({"constraint": constraint["name"],
                                           "reason": f"{scope} is forbidden by {prefix}"})
            elif constraint["kind"] == "quiet_hours":
                start, end = int(spec.get("start", 22)), int(spec.get("end", 7))
                hour = now.tm_hour
                inside = (start <= hour or hour < end) if start > end else (start <= hour < end)
                if inside and scope.startswith(tuple(spec.get("scopes", ["notify"]))):
                    violations.append({"constraint": constraint["name"],
                                       "reason": f"quiet hours {start}:00-{end}:00"})
            elif constraint["kind"] == "require_approval":
                for prefix in spec.get("scopes", []):
                    if scope.startswith(prefix):
                        approvals.append(constraint["name"])
        return {"allowed": not violations, "violations": violations,
                "requires_approval": approvals}

    def enforce(self, scope: str) -> None:
        result = self.check_constraints(scope)
        if not result["allowed"]:
            raise ConstraintViolation(result["violations"][0]["reason"])

    # ---------------- user permissions ----------------
    def set_permission(self, scope: str, allowed: bool, reason: str = "") -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO user_permissions(scope, subject, allowed, reason, created_at)"
                " VALUES(?,?,?,?,?) ON CONFLICT(scope) DO UPDATE SET allowed=excluded.allowed,"
                " reason=excluded.reason",
                (scope, self.subject, int(bool(allowed)), reason, _utc()),
            )
            self._conn.commit()

    def permission(self, scope: str) -> Optional[bool]:
        """Longest-prefix match, so `files.delete` can be denied while `files` is allowed."""
        with self._lock:
            rows = self._conn.execute("SELECT scope, allowed FROM user_permissions WHERE subject=?",
                                      (self.subject,)).fetchall()
        best: Optional[sqlite3.Row] = None
        for row in rows:
            if scope == row["scope"] or scope.startswith(row["scope"]):
                if best is None or len(row["scope"]) > len(best["scope"]):
                    best = row
        return None if best is None else bool(best["allowed"])

    # ---------------- expertise ----------------
    def record_interaction(self, topic: str, success: bool,
                           depth: str = "normal") -> Dict[str, Any]:
        """Expertise moves only on real interaction evidence."""
        weight = {"basic": 0.5, "normal": 1.0, "advanced": 1.6}.get(depth, 1.0)
        with self._lock:
            row = self._conn.execute("SELECT * FROM expertise WHERE topic=? AND subject=?",
                                     (topic, self.subject)).fetchone()
            samples = (row["samples"] if row else 0) + 1
            successes = (row["successes"] if row else 0) + (1 if success else 0)
            prior = row["score"] if row else 0.25
            target = min(1.0, (successes / samples) * (0.6 + 0.4 * weight))
            score = round(prior + (target - prior) / min(samples, 8), 4)
            self._conn.execute(
                "INSERT INTO expertise(topic, subject, score, samples, successes, updated_at)"
                " VALUES(?,?,?,?,?,?) ON CONFLICT(topic) DO UPDATE SET score=excluded.score,"
                " samples=excluded.samples, successes=excluded.successes,"
                " updated_at=excluded.updated_at",
                (topic, self.subject, score, samples, successes, _utc()),
            )
            self._conn.commit()
        return self.expertise(topic)

    def expertise(self, topic: str) -> Dict[str, Any]:
        with self._lock:
            row = self._conn.execute("SELECT * FROM expertise WHERE topic=? AND subject=?",
                                     (topic, self.subject)).fetchone()
        if row is None:
            return {"topic": topic, "score": None, "level": "unknown", "samples": 0,
                    "evidence": "no interactions recorded"}
        level = EXPERTISE_LEVELS[0][1]
        for threshold, name in EXPERTISE_LEVELS:
            if row["score"] >= threshold:
                level = name
        confident = row["samples"] >= MIN_EVIDENCE
        return {"topic": topic, "score": row["score"], "level": level if confident else "unconfirmed",
                "samples": row["samples"], "successes": row["successes"],
                "evidence": f"{row['successes']}/{row['samples']} successful interactions"}

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            rows = self._conn.execute("SELECT * FROM attributes WHERE subject=?",
                                      (self.subject,)).fetchall()
        # Expired temporary preferences are omitted: snapshot() is what the
        # policy layer and "what do you know about me" both read, and a lapsed
        # preference must not influence either.
        return {row["key"]: {"value": json.loads(row["value"]), "confidence": row["confidence"],
                             "source": row["source"], "version": row["version"],
                             "expires_at": (row["expires_at"] if "expires_at" in row.keys() else None),
                             "temporary": bool(row["expires_at"] if "expires_at" in row.keys() else None)}
                for row in rows
                if not _expired(row["expires_at"] if "expires_at" in row.keys() else None)}


# --------------------------------------------------------------------------- personality
CORE_TRAITS = {
    "identity": "Jarvis",
    "loyalty": "owner-first",
    "honesty": "never claims unverified success",
    "respect": "always addresses the owner politely",
    "safety": "refuses destructive actions without approval",
}

# presentation knobs the conversation layer MAY vary
ADAPTABLE = ("tone", "verbosity", "technical_depth", "pace", "offer_help", "style")


class Personality:
    """Stable core + adaptable presentation, identical on every surface."""

    def __init__(self, profile: Optional[ProfileStore] = None) -> None:
        self.profile = profile
        self.core = dict(CORE_TRAITS)

    def constrain(self, directives: Dict[str, Any]) -> Dict[str, Any]:
        """Strip anything that would change the core personality."""
        cleaned = {k: v for k, v in directives.items() if k in ADAPTABLE}
        if self.profile is not None:
            preferred = self.profile.get("communication.verbosity")
            if preferred and "verbosity" not in directives:
                cleaned["verbosity"] = preferred
        return cleaned

    def render(self, surface: str, directives: Dict[str, Any]) -> Dict[str, Any]:
        """Profile for a surface (gui/voice/text/android/agent).

        Surfaces may only change *delivery* (e.g. voice is more concise);
        the core traits are identical everywhere, which is the consistency
        guarantee.
        """
        if surface not in ("gui", "voice", "text", "android", "agent"):
            raise ValueError(f"unknown surface {surface!r}")
        out = {"core": dict(self.core), "surface": surface}
        adapted = self.constrain(directives)
        if surface in ("voice", "android"):
            adapted["verbosity"] = "concise" if adapted.get("verbosity") == "detailed" else \
                adapted.get("verbosity", "concise")
        if surface == "agent":
            adapted["offer_help"] = False  # background agents never chat
        out["presentation"] = adapted
        return out

    def consistent(self, renders: Sequence[Dict[str, Any]]) -> bool:
        """True when every surface reports the same core identity/values."""
        cores = [json.dumps(r["core"], sort_keys=True) for r in renders]
        return len(set(cores)) == 1

    def emotional_context(self, mood: Dict[str, Any]) -> Dict[str, Any]:
        """Translate conversation mood into a response policy."""
        dominant = mood.get("dominant", "neutral")
        policy = {
            "frustrated": {"acknowledge": True, "apologise": True, "skip_small_talk": True},
            "confused": {"acknowledge": True, "explain_more": True, "use_example": True},
            "excited": {"acknowledge": True, "match_energy": True},
            "urgent": {"acknowledge": False, "skip_small_talk": True, "answer_first": True},
            "neutral": {"acknowledge": False},
        }.get(dominant, {"acknowledge": False})
        return {"dominant": dominant, "policy": policy,
                "confidence": round(float(mood.get("signals", {}).get(dominant, 0.0)), 4)}


_PROFILE: Optional[ProfileStore] = None
_PROFILE_LOCK = threading.RLock()


def get_profile_store(**kwargs: Any) -> ProfileStore:
    global _PROFILE
    with _PROFILE_LOCK:
        if _PROFILE is None:
            _PROFILE = ProfileStore(**kwargs)
        return _PROFILE
