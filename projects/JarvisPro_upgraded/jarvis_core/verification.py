"""Verification engine (Section 19).

Every significant action can produce evidence:
  action / expected result / actual result / evidence / confidence / timestamp

Verifiers are real checks (file exists, file hash, file contains, value
equality, JSON field, process alive, callable predicate). Nothing returns a
bare True: a verification always records what was expected, what was actually
observed, the raw evidence string and a confidence, and the history is
persisted so it can be audited later.

State: SQLite `verification.db`, table `verifications`.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

_DEF_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")

RESULT_VERIFIED = "verified"
RESULT_FAILED = "failed"
RESULT_INCONCLUSIVE = "inconclusive"
RESULT_UNSUPPORTED = "unsupported"

# Direct observation beats indirect inference: a hash match is stronger
# evidence than "the file exists".
KIND_CONFIDENCE = {
    "file_hash": 0.99,
    "value_equals": 0.95,
    "file_contains": 0.93,
    "json_field": 0.9,
    "file_exists": 0.85,
    "process_alive": 0.8,
    "predicate": 0.75,
}


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class Verification:
    id: str
    action: str
    kind: str
    expected: Any
    actual: Any
    result: str
    confidence: float
    evidence: str
    trace_id: Optional[str] = None
    task_id: Optional[str] = None
    timestamp: str = field(default_factory=_utc)

    @property
    def verified(self) -> bool:
        return self.result == RESULT_VERIFIED

    def to_dict(self) -> Dict[str, Any]:
        return {"id": self.id, "action": self.action, "kind": self.kind,
                "expected": self.expected, "actual": self.actual, "result": self.result,
                "verified": self.verified, "confidence": round(self.confidence, 4),
                "evidence": self.evidence, "trace_id": self.trace_id,
                "task_id": self.task_id, "timestamp": self.timestamp}


class VerificationEngine:
    """Called by the execution engine, managers and agents after each action."""

    def __init__(self, db_path: Optional[str] = None, kernel: Any = None):
        self.kernel = kernel
        path = db_path or os.path.join(_DEF_DIR, "verification.db")
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS verifications(
                    id TEXT PRIMARY KEY, action TEXT, kind TEXT, expected TEXT,
                    actual TEXT, result TEXT, confidence REAL, evidence TEXT,
                    trace_id TEXT, task_id TEXT, timestamp TEXT);
                CREATE INDEX IF NOT EXISTS idx_verif_action ON verifications(action);
                CREATE INDEX IF NOT EXISTS idx_verif_trace ON verifications(trace_id);
                """
            )
            self._conn.commit()

    # ---------------- single check ----------------
    def verify(self, action: str, kind: str, expected: Any = None, *,
               path: Optional[str] = None, value: Any = None,
               predicate: Optional[Callable[[], Any]] = None,
               pid: Optional[int] = None, field_path: Optional[str] = None,
               trace_id: Optional[str] = None,
               task_id: Optional[str] = None) -> Verification:
        """Run one real check and record it. Unknown kinds are 'unsupported'."""
        if not isinstance(action, str) or not action.strip():
            raise ValueError("action must be a non-empty string")
        actual: Any = None
        result = RESULT_FAILED
        evidence = ""
        try:
            if kind == "file_exists":
                if not path:
                    raise ValueError("file_exists requires path")
                actual = os.path.isfile(path)
                result = RESULT_VERIFIED if actual == bool(True if expected is None else expected) \
                    else RESULT_FAILED
                evidence = f"os.path.isfile({path!r}) -> {actual}"
            elif kind == "file_hash":
                if not path:
                    raise ValueError("file_hash requires path")
                if not os.path.isfile(path):
                    evidence = f"{path} does not exist"
                else:
                    with open(path, "rb") as fh:
                        actual = hashlib.sha256(fh.read()).hexdigest()
                    result = RESULT_VERIFIED if actual == expected else RESULT_FAILED
                    evidence = f"sha256({path})={actual}"
            elif kind == "file_contains":
                if not path:
                    raise ValueError("file_contains requires path")
                if not os.path.isfile(path):
                    evidence = f"{path} does not exist"
                else:
                    with open(path, "r", encoding="utf-8", errors="ignore") as fh:
                        body = fh.read()
                    actual = str(expected) in body
                    result = RESULT_VERIFIED if actual else RESULT_FAILED
                    evidence = f"{path} ({len(body)} chars) contains {expected!r} -> {actual}"
            elif kind == "value_equals":
                actual = value
                result = RESULT_VERIFIED if value == expected else RESULT_FAILED
                evidence = f"observed {value!r} vs expected {expected!r}"
            elif kind == "json_field":
                cursor = value
                for part in (field_path or "").split("."):
                    if part == "":
                        continue
                    if isinstance(cursor, dict) and part in cursor:
                        cursor = cursor[part]
                    else:
                        cursor = None
                        break
                actual = cursor
                result = RESULT_VERIFIED if cursor == expected else RESULT_FAILED
                evidence = f"{field_path}={cursor!r} vs expected {expected!r}"
            elif kind == "process_alive":
                if pid is None:
                    raise ValueError("process_alive requires pid")
                try:
                    os.kill(int(pid), 0)
                    actual = True
                except ProcessLookupError:
                    actual = False
                except PermissionError:
                    actual = True  # exists but owned by another user
                result = RESULT_VERIFIED if actual == bool(expected) else RESULT_FAILED
                evidence = f"os.kill({pid}, 0) alive={actual}"
            elif kind == "predicate":
                if predicate is None or not callable(predicate):
                    raise ValueError("predicate kind requires a callable")
                actual = predicate()
                result = RESULT_VERIFIED if bool(actual) else RESULT_FAILED
                evidence = f"predicate returned {actual!r}"
            else:
                result = RESULT_UNSUPPORTED
                evidence = f"no verifier for kind {kind!r}"
        except Exception as exc:
            result = RESULT_INCONCLUSIVE
            evidence = f"check raised {type(exc).__name__}: {exc}"
        confidence = (KIND_CONFIDENCE.get(kind, 0.5) if result == RESULT_VERIFIED
                      else 0.0 if result == RESULT_FAILED else 0.2)
        record = Verification(
            id="VF-" + uuid.uuid4().hex[:10], action=action.strip(), kind=kind,
            expected=expected, actual=actual, result=result, confidence=confidence,
            evidence=evidence, trace_id=trace_id, task_id=task_id,
        )
        self._store(record)
        return record

    # ---------------- multiple checks for one action ----------------
    def verify_all(self, action: str, checks: List[Dict[str, Any]], *,
                   trace_id: Optional[str] = None,
                   task_id: Optional[str] = None) -> Dict[str, Any]:
        """Run several checks for one action.

        The action counts as verified only if every check passed; confidence is
        the weakest passing check, because a chain is only as strong as its
        weakest evidence.
        """
        if not checks:
            return {"action": action, "verified": False, "confidence": 0.0,
                    "reason": "no checks supplied - nothing was verified",
                    "checks": []}
        records = []
        for spec in checks:
            spec = dict(spec)
            kind = spec.pop("kind", "")
            expected = spec.pop("expected", None)
            records.append(self.verify(action, kind, expected, trace_id=trace_id,
                                       task_id=task_id, **spec))
        verified = all(r.verified for r in records)
        confidence = min((r.confidence for r in records), default=0.0)
        failures = [r.to_dict() for r in records if not r.verified]
        return {"action": action, "verified": verified, "confidence": round(confidence, 4),
                "checks": [r.to_dict() for r in records], "failures": failures,
                "reason": ("all checks passed" if verified else
                           "; ".join(f"{f['kind']}: {f['evidence']}" for f in failures))}

    # ---------------- history ----------------
    def _store(self, record: Verification) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO verifications(id, action, kind, expected, actual, result,"
                " confidence, evidence, trace_id, task_id, timestamp)"
                " VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (record.id, record.action, record.kind,
                 json.dumps(record.expected, default=str),
                 json.dumps(record.actual, default=str), record.result,
                 record.confidence, record.evidence, record.trace_id, record.task_id,
                 record.timestamp))
            self._conn.commit()
        analytics = getattr(self.kernel, "analytics", None)
        if analytics is not None:
            try:
                analytics.record("verification", record.action, record.verified,
                                 trace_id=record.trace_id,
                                 error=None if record.verified else record.evidence)
            except Exception:
                pass

    def history(self, action: Optional[str] = None, trace_id: Optional[str] = None,
                limit: int = 50) -> List[Dict[str, Any]]:
        sql = "SELECT * FROM verifications"
        clauses: List[str] = []
        params: List[Any] = []
        if action:
            clauses.append("action=?")
            params.append(action)
        if trace_id:
            clauses.append("trace_id=?")
            params.append(trace_id)
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY timestamp DESC, id DESC LIMIT ?"
        params.append(int(limit))
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        out = []
        for row in rows:
            item = dict(row)
            for key in ("expected", "actual"):
                try:
                    item[key] = json.loads(item[key]) if item[key] is not None else None
                except (TypeError, json.JSONDecodeError):
                    pass
            item["verified"] = item["result"] == RESULT_VERIFIED
            out.append(item)
        return out

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT result, COUNT(*) AS n FROM verifications GROUP BY result").fetchall()
            total = self._conn.execute("SELECT COUNT(*) AS n FROM verifications").fetchone()["n"]
        by_result = {r["result"]: r["n"] for r in rows}
        verified = by_result.get(RESULT_VERIFIED, 0)
        return {"total": total, "by_result": by_result,
                "verified_rate": round(verified / total, 4) if total else 0.0}

    def health(self) -> Dict[str, Any]:
        return {"available": True, **self.stats()}


__all__ = ["VerificationEngine", "Verification", "RESULT_VERIFIED", "RESULT_FAILED",
           "RESULT_INCONCLUSIVE", "RESULT_UNSUPPORTED", "KIND_CONFIDENCE"]
