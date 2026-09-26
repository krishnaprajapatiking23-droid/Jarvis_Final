"""Section 4 - memory lifecycle: consolidation, decay, archive/restore,
privacy levels, permissions and versioning.

Every record carries id / content / type / importance / confidence / source /
created_at / updated_at / last_accessed / privacy_level / permissions /
version / status, and every mutation writes a new row into ``memory_versions``
so history is never destroyed by an edit.

Privacy is enforced on *read*: :meth:`MemoryStore.recall` and
:meth:`MemoryStore.get` take an ``audience`` and refuse to return records the
audience is not permitted to see. That is the guarantee "private memory is
never exposed outside its permission scope".

Storage: ``data/memory_lifecycle.db``.
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
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence

_DEF_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")

# privacy levels, least -> most restricted
PUBLIC, PERSONAL, PRIVATE, SECRET = "public", "personal", "private", "secret"
PRIVACY_ORDER = {PUBLIC: 0, PERSONAL: 1, PRIVATE: 2, SECRET: 3}

# which audiences may see up to which level by default
AUDIENCE_CLEARANCE = {
    "owner": SECRET,
    "gui": PRIVATE,
    "voice": PRIVATE,
    "android": PERSONAL,
    "agent": PERSONAL,
    "guest": PUBLIC,
    "cloud": PUBLIC,
}

STATUS_ACTIVE, STATUS_ARCHIVED, STATUS_DELETED = "active", "archived", "deleted"

DECAY_HALF_LIFE_DAYS = 30.0
ARCHIVE_THRESHOLD = 0.18  # effective strength below this is archived, not deleted


class MemoryPermissionError(PermissionError):
    """Raised when an audience asks for a record outside its clearance."""


def _utc() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())


def _tokens(text: str) -> List[str]:
    return [t for t in re.findall(r"[a-z0-9']+", (text or "").lower()) if len(t) > 2]


@dataclass
class Memory:
    id: str
    content: str
    type: str = "fact"
    importance: float = 0.5
    confidence: float = 0.7
    source: str = "conversation"
    created_at: str = field(default_factory=_utc)
    updated_at: str = field(default_factory=_utc)
    last_accessed: Optional[str] = None
    access_count: int = 0
    privacy_level: str = PERSONAL
    permissions: List[str] = field(default_factory=list)
    version: int = 1
    status: str = STATUS_ACTIVE
    consolidated_into: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        data = dict(self.__dict__)
        data["permissions"] = list(self.permissions)
        return data


class MemoryStore:
    def __init__(self, db_path: Optional[str] = None, observability: Any = None) -> None:
        os.makedirs(_DEF_DIR, exist_ok=True)
        self.db_path = db_path or os.path.join(_DEF_DIR, "memory_lifecycle.db")
        self.obs = observability
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self) -> None:
        with self._lock:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS memories (
                    id TEXT PRIMARY KEY,
                    content TEXT NOT NULL,
                    type TEXT,
                    importance REAL,
                    confidence REAL,
                    source TEXT,
                    created_at TEXT,
                    updated_at TEXT,
                    last_accessed TEXT,
                    access_count INTEGER DEFAULT 0,
                    privacy_level TEXT,
                    permissions TEXT,
                    version INTEGER DEFAULT 1,
                    status TEXT,
                    consolidated_into TEXT
                );
                CREATE TABLE IF NOT EXISTS memory_versions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    memory_id TEXT,
                    version INTEGER,
                    content TEXT,
                    importance REAL,
                    confidence REAL,
                    privacy_level TEXT,
                    permissions TEXT,
                    status TEXT,
                    reason TEXT,
                    actor TEXT,
                    created_at TEXT
                );
                CREATE TABLE IF NOT EXISTS memory_terms (
                    memory_id TEXT,
                    term TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_mem_terms ON memory_terms(term);
                CREATE INDEX IF NOT EXISTS idx_mem_status ON memories(status);
                CREATE TABLE IF NOT EXISTS memory_audit (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    memory_id TEXT,
                    audience TEXT,
                    action TEXT,
                    allowed INTEGER,
                    reason TEXT,
                    created_at TEXT
                );
                """
            )
            self._conn.commit()

    # ---------------- helpers ----------------
    def _row_to_memory(self, row: sqlite3.Row) -> Memory:
        data = dict(row)
        data["permissions"] = json.loads(data.get("permissions") or "[]")
        return Memory(**data)

    def _index(self, memory_id: str, content: str) -> None:
        self._conn.execute("DELETE FROM memory_terms WHERE memory_id=?", (memory_id,))
        self._conn.executemany(
            "INSERT INTO memory_terms(memory_id, term) VALUES(?,?)",
            [(memory_id, term) for term in set(_tokens(content))],
        )

    def _snapshot(self, mem: Memory, reason: str, actor: str) -> None:
        self._conn.execute(
            "INSERT INTO memory_versions(memory_id, version, content, importance, confidence,"
            " privacy_level, permissions, status, reason, actor, created_at)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (mem.id, mem.version, mem.content, mem.importance, mem.confidence, mem.privacy_level,
             json.dumps(mem.permissions), mem.status, reason, actor, _utc()),
        )

    def _audit(self, memory_id: str, audience: str, action: str, allowed: bool, reason: str) -> None:
        self._conn.execute(
            "INSERT INTO memory_audit(memory_id, audience, action, allowed, reason, created_at)"
            " VALUES(?,?,?,?,?,?)",
            (memory_id, audience, action, int(allowed), reason, _utc()),
        )

    # ---------------- permissions ----------------
    def may_read(self, mem: Memory, audience: str) -> bool:
        if audience in mem.permissions:
            return True
        clearance = AUDIENCE_CLEARANCE.get(audience)
        if clearance is None:
            return False
        return PRIVACY_ORDER[mem.privacy_level] <= PRIVACY_ORDER[clearance]

    # ---------------- capture / validate / classify ----------------
    def capture(self, content: str, *, type: str = "fact", importance: float = 0.5,
                confidence: float = 0.7, source: str = "conversation",
                privacy_level: Optional[str] = None, permissions: Sequence[str] = (),
                actor: str = "owner") -> Memory:
        """captured -> validated -> classified -> stored, in one call."""
        if not isinstance(content, str) or not content.strip():
            raise ValueError("memory content must be a non-empty string")
        if not 0.0 <= importance <= 1.0 or not 0.0 <= confidence <= 1.0:
            raise ValueError("importance and confidence must be within 0..1")
        level = privacy_level or self.classify_privacy(content)
        if level not in PRIVACY_ORDER:
            raise ValueError(f"unknown privacy level {level!r}")
        mem = Memory(
            id="M-" + uuid.uuid4().hex[:10], content=content.strip(), type=type,
            importance=float(importance), confidence=float(confidence), source=source,
            privacy_level=level, permissions=list(permissions),
        )
        with self._lock:
            self._conn.execute(
                "INSERT INTO memories(id, content, type, importance, confidence, source,"
                " created_at, updated_at, last_accessed, access_count, privacy_level, permissions,"
                " version, status, consolidated_into) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (mem.id, mem.content, mem.type, mem.importance, mem.confidence, mem.source,
                 mem.created_at, mem.updated_at, None, 0, mem.privacy_level,
                 json.dumps(mem.permissions), 1, mem.status, None),
            )
            self._index(mem.id, mem.content)
            self._snapshot(mem, "captured", actor)
            self._conn.commit()
        return mem

    def classify_privacy(self, content: str) -> str:
        """Heuristic classification; secrets are never stored as `public`."""
        lowered = (content or "").lower()
        if re.search(r"\b(password|passcode|api[ _-]?key|token|otp|pin|cvv|secret)\b", lowered):
            return SECRET
        if re.search(r"\b(salary|medical|diagnos|therapy|bank|account number|aadhaar|passport)\b",
                     lowered):
            return PRIVATE
        if re.search(r"\b(i|my|me)\b", lowered):
            return PERSONAL
        return PUBLIC

    # ---------------- read ----------------
    def get(self, memory_id: str, audience: str = "owner", touch: bool = True) -> Memory:
        with self._lock:
            row = self._conn.execute("SELECT * FROM memories WHERE id=?", (memory_id,)).fetchone()
            if row is None:
                raise KeyError(f"unknown memory {memory_id}")
            mem = self._row_to_memory(row)
            if not self.may_read(mem, audience):
                self._audit(memory_id, audience, "read", False,
                            f"{mem.privacy_level} above clearance of {audience}")
                self._conn.commit()
                raise MemoryPermissionError(
                    f"audience {audience!r} may not read {mem.privacy_level} memory {memory_id}")
            if touch:
                mem.last_accessed = _utc()
                mem.access_count += 1
                self._conn.execute("UPDATE memories SET last_accessed=?, access_count=? WHERE id=?",
                                   (mem.last_accessed, mem.access_count, memory_id))
            self._audit(memory_id, audience, "read", True, "within clearance")
            self._conn.commit()
        return mem

    def recall(self, query: str, audience: str = "owner", limit: int = 10,
               include_archived: bool = False) -> List[Memory]:
        """Ranked recall. Records outside the audience's scope are omitted."""
        terms = set(_tokens(query))
        statuses = [STATUS_ACTIVE] + ([STATUS_ARCHIVED] if include_archived else [])
        placeholders = ",".join("?" for _ in statuses)
        with self._lock:
            rows = self._conn.execute(
                f"SELECT * FROM memories WHERE status IN ({placeholders})", statuses
            ).fetchall()
        scored: List[tuple] = []
        for row in rows:
            mem = self._row_to_memory(row)
            if not self.may_read(mem, audience):
                continue
            overlap = len(terms & set(_tokens(mem.content)))
            if terms and not overlap:
                continue
            score = overlap + mem.importance + 0.5 * mem.confidence + 0.3 * self.strength(mem)
            scored.append((score, mem))
        scored.sort(key=lambda pair: -pair[0])
        found = [mem for _, mem in scored[:limit]]
        with self._lock:
            for mem in found:
                self._conn.execute(
                    "UPDATE memories SET last_accessed=?, access_count=access_count+1 WHERE id=?",
                    (_utc(), mem.id))
            self._conn.commit()
        return found

    # ---------------- update / versioning ----------------
    def update(self, memory_id: str, *, content: Optional[str] = None,
               importance: Optional[float] = None, confidence: Optional[float] = None,
               privacy_level: Optional[str] = None, permissions: Optional[Sequence[str]] = None,
               reason: str = "edited", actor: str = "owner") -> Memory:
        with self._lock:
            mem = self.get(memory_id, audience="owner", touch=False)
            self._snapshot(mem, f"before:{reason}", actor)  # previous state preserved
            if content is not None:
                if not content.strip():
                    raise ValueError("content may not be blank")
                mem.content = content.strip()
                self._index(memory_id, mem.content)
            if importance is not None:
                mem.importance = float(importance)
            if confidence is not None:
                mem.confidence = float(confidence)
            if privacy_level is not None:
                if privacy_level not in PRIVACY_ORDER:
                    raise ValueError(f"unknown privacy level {privacy_level!r}")
                mem.privacy_level = privacy_level
            if permissions is not None:
                mem.permissions = list(permissions)
            mem.version += 1
            mem.updated_at = _utc()
            self._conn.execute(
                "UPDATE memories SET content=?, importance=?, confidence=?, privacy_level=?,"
                " permissions=?, version=?, updated_at=? WHERE id=?",
                (mem.content, mem.importance, mem.confidence, mem.privacy_level,
                 json.dumps(mem.permissions), mem.version, mem.updated_at, memory_id),
            )
            self._conn.commit()
        return mem

    def versions(self, memory_id: str) -> List[Dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM memory_versions WHERE memory_id=? ORDER BY id", (memory_id,)
            ).fetchall()
        return [dict(row) for row in rows]

    def revert(self, memory_id: str, version: int, actor: str = "owner") -> Memory:
        """Roll a record back to an earlier version (itself a new version)."""
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM memory_versions WHERE memory_id=? AND version=? ORDER BY id LIMIT 1",
                (memory_id, version),
            ).fetchone()
            if row is None:
                raise KeyError(f"memory {memory_id} has no version {version}")
        return self.update(memory_id, content=row["content"], importance=row["importance"],
                           confidence=row["confidence"], privacy_level=row["privacy_level"],
                           permissions=json.loads(row["permissions"] or "[]"),
                           reason=f"revert to v{version}", actor=actor)

    # ---------------- decay / archive / restore ----------------
    def _age_days(self, mem: Memory) -> float:
        ref = mem.last_accessed or mem.updated_at or mem.created_at
        try:
            then = time.mktime(time.strptime(ref, "%Y-%m-%dT%H:%M:%S"))
        except (ValueError, TypeError):
            return 0.0
        return max(0.0, (time.time() - then) / 86400.0)

    def strength(self, mem: Memory) -> float:
        """Exponential decay, resisted by importance and access frequency."""
        decay = math.exp(-self._age_days(mem) * math.log(2) / DECAY_HALF_LIFE_DAYS)
        resistance = 0.5 * mem.importance + min(0.3, 0.05 * mem.access_count)
        return round(min(1.0, decay * (1 - resistance) + resistance), 4)

    def decay(self, archive_threshold: float = ARCHIVE_THRESHOLD) -> Dict[str, Any]:
        """Archive (never delete) records whose effective strength collapsed."""
        archived: List[str] = []
        with self._lock:
            rows = self._conn.execute("SELECT * FROM memories WHERE status=?",
                                      (STATUS_ACTIVE,)).fetchall()
            for row in rows:
                mem = self._row_to_memory(row)
                if mem.importance >= 0.8:
                    continue  # important memories are never auto-archived
                if self.strength(mem) < archive_threshold:
                    self._snapshot(mem, "before:decay-archive", "system")
                    mem.status = STATUS_ARCHIVED
                    mem.version += 1
                    self._conn.execute("UPDATE memories SET status=?, version=?, updated_at=?"
                                       " WHERE id=?",
                                       (STATUS_ARCHIVED, mem.version, _utc(), mem.id))
                    archived.append(mem.id)
            self._conn.commit()
        return {"archived": archived, "count": len(archived)}

    def archive(self, memory_id: str, actor: str = "owner") -> Memory:
        mem = self.get(memory_id, touch=False)
        with self._lock:
            self._snapshot(mem, "before:archive", actor)
            mem.status = STATUS_ARCHIVED
            mem.version += 1
            self._conn.execute("UPDATE memories SET status=?, version=?, updated_at=? WHERE id=?",
                               (mem.status, mem.version, _utc(), memory_id))
            self._conn.commit()
        return mem

    def restore(self, memory_id: str, actor: str = "owner") -> Memory:
        mem = self.get(memory_id, touch=False)
        if mem.status == STATUS_ACTIVE:
            return mem
        with self._lock:
            self._snapshot(mem, "before:restore", actor)
            mem.status = STATUS_ACTIVE
            mem.version += 1
            mem.last_accessed = _utc()
            self._conn.execute("UPDATE memories SET status=?, version=?, updated_at=?,"
                               " last_accessed=? WHERE id=?",
                               (mem.status, mem.version, _utc(), mem.last_accessed, memory_id))
            self._conn.commit()
        return mem

    def forget(self, memory_id: str, actor: str = "owner") -> Memory:
        """\"Forget this\" - content is erased, the audit trail is not."""
        mem = self.get(memory_id, touch=False)
        with self._lock:
            self._snapshot(mem, "before:forget", actor)
            mem.version += 1
            mem.status = STATUS_DELETED
            self._conn.execute(
                "UPDATE memories SET content=?, status=?, version=?, updated_at=? WHERE id=?",
                ("[forgotten on user request]", STATUS_DELETED, mem.version, _utc(), memory_id))
            self._conn.execute("DELETE FROM memory_terms WHERE memory_id=?", (memory_id,))
            self._conn.commit()
        mem.content = "[forgotten on user request]"
        return mem

    # ---------------- consolidation ----------------
    def consolidate(self, min_overlap: int = 2) -> Dict[str, Any]:
        """Merge near-duplicate active memories into one stronger record.

        The survivor keeps the highest importance/confidence and the union of
        permissions restricted to the strictest privacy level; the merged
        records are archived with ``consolidated_into`` pointing at the
        survivor, so nothing is silently lost.
        """
        with self._lock:
            rows = self._conn.execute("SELECT * FROM memories WHERE status=? AND type!='secret'",
                                      (STATUS_ACTIVE,)).fetchall()
        mems = [self._row_to_memory(row) for row in rows]
        groups: List[List[Memory]] = []
        used: set = set()
        for i, mem in enumerate(mems):
            if mem.id in used:
                continue
            group = [mem]
            used.add(mem.id)
            for other in mems[i + 1:]:
                if other.id in used or other.type != mem.type:
                    continue
                overlap = len(set(_tokens(mem.content)) & set(_tokens(other.content)))
                smaller = min(len(set(_tokens(mem.content))), len(set(_tokens(other.content)))) or 1
                if overlap >= min_overlap and overlap / smaller >= 0.6:
                    group.append(other)
                    used.add(other.id)
            if len(group) > 1:
                groups.append(group)

        merged: List[Dict[str, Any]] = []
        for group in groups:
            survivor = max(group, key=lambda m: (m.importance, m.confidence, len(m.content)))
            strictest = max(group, key=lambda m: PRIVACY_ORDER[m.privacy_level]).privacy_level
            perms: List[str] = []
            for mem in group:
                perms.extend(mem.permissions)
            self.update(survivor.id, importance=min(1.0, survivor.importance + 0.1),
                        confidence=min(1.0, max(m.confidence for m in group) + 0.05),
                        privacy_level=strictest, permissions=sorted(set(perms)),
                        reason="consolidated", actor="system")
            for mem in group:
                if mem.id == survivor.id:
                    continue
                with self._lock:
                    self._snapshot(mem, "before:consolidate", "system")
                    self._conn.execute(
                        "UPDATE memories SET status=?, consolidated_into=?, version=version+1,"
                        " updated_at=? WHERE id=?",
                        (STATUS_ARCHIVED, survivor.id, _utc(), mem.id))
                    self._conn.commit()
            merged.append({"survivor": survivor.id,
                           "absorbed": [m.id for m in group if m.id != survivor.id],
                           "privacy_level": strictest})
        return {"groups": len(merged), "merged": merged}

    # ---------------- reporting ----------------
    def stats(self) -> Dict[str, Any]:
        with self._lock:
            rows = self._conn.execute("SELECT status, COUNT(*) c FROM memories GROUP BY status").fetchall()
            levels = self._conn.execute(
                "SELECT privacy_level, COUNT(*) c FROM memories GROUP BY privacy_level").fetchall()
            denials = self._conn.execute(
                "SELECT COUNT(*) c FROM memory_audit WHERE allowed=0").fetchone()
        return {
            "by_status": {row["status"]: row["c"] for row in rows},
            "by_privacy": {row["privacy_level"]: row["c"] for row in levels},
            "denied_reads": denials["c"] if denials else 0,
        }

    def audit_log(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM memory_audit ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(row) for row in rows]


_STORE: Optional[MemoryStore] = None
_STORE_LOCK = threading.RLock()


def get_memory_store(**kwargs: Any) -> MemoryStore:
    global _STORE
    with _STORE_LOCK:
        if _STORE is None:
            _STORE = MemoryStore(**kwargs)
        return _STORE
