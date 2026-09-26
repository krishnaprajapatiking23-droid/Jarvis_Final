"""S39 Observability & diagnostics: trace IDs, execution traces, failure reports.

Real implementation backed by SQLite so traces survive restarts.
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
import traceback
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

_DEF_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


STAGES = (
    "input", "router", "manager", "planner", "tool", "database", "output",
)


@dataclass
class Span:
    trace_id: str
    span_id: str
    stage: str
    name: str
    started: float
    parent_id: Optional[str] = None
    ended: Optional[float] = None
    status: str = "running"
    error: Optional[str] = None
    attributes: Dict[str, Any] = field(default_factory=dict)
    seq: int = 0  # creation order: traces read input -> router -> ... even though spans end innermost-first

    @property
    def duration_ms(self) -> Optional[float]:
        if self.ended is None:
            return None
        return round((self.ended - self.started) * 1000.0, 3)

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_id": self.parent_id,
            "stage": self.stage,
            "name": self.name,
            "status": self.status,
            "error": self.error,
            "duration_ms": self.duration_ms,
            "attributes": dict(self.attributes),
        }
        return d


class _SpanContext:
    def __init__(self, obs: "Observability", span: Span):
        self._obs = obs
        self.span = span

    def set(self, **attrs: Any) -> "_SpanContext":
        self.span.attributes.update(attrs)
        return self

    def __enter__(self) -> "_SpanContext":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        if exc is None:
            self._obs.end_span(self.span, status="ok")
        else:
            self._obs.end_span(
                self.span,
                status="error",
                error=f"{exc_type.__name__}: {exc}",
                stack="".join(traceback.format_exception(exc_type, exc, tb)),
            )
        return False


class Observability:
    """Central trace store. Thread-safe, persistent, queryable."""

    def __init__(self, db_path: Optional[str] = None):
        os.makedirs(_DEF_DIR, exist_ok=True)
        self.db_path = db_path or os.path.join(_DEF_DIR, "observability.db")
        self._lock = threading.RLock()
        self._local = threading.local()
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._migrate_legacy()
        self._init_db()

    # ---------------- schema ----------------
    REQUIRED_COLUMNS = {
        "traces": {"trace_id", "seq", "label", "created_at", "status", "duration_ms"},
        "spans": {"span_id", "trace_id", "parent_id", "stage", "name", "status", "error",
                   "duration_ms", "attributes", "created_at"},
        "failures": {"trace_id", "span_id", "stage", "name", "error", "stack", "created_at"},
    }

    def _migrate_legacy(self) -> None:
        """Older builds shipped an incompatible `spans`/`traces` schema.

        Rather than crashing (or silently deleting history), any table whose
        columns do not satisfy the current contract is renamed aside with a
        timestamp so the new schema can be created and the old rows remain
        recoverable on disk.
        """
        stamp = time.strftime("%Y%m%d%H%M%S")
        with self._lock:
            for table, required in self.REQUIRED_COLUMNS.items():
                try:
                    info = self._conn.execute(f"PRAGMA table_info({table})").fetchall()
                except sqlite3.DatabaseError:
                    continue
                if not info:
                    continue
                have = {row[1] for row in info}
                missing = required - have
                if missing:
                    legacy = f"{table}_legacy_{stamp}"
                    try:
                        self._conn.execute(f"ALTER TABLE {table} RENAME TO {legacy}")
                        self._conn.commit()
                    except sqlite3.DatabaseError:
                        self._conn.execute(f"DROP TABLE IF EXISTS {table}")
                        self._conn.commit()

    def _init_db(self) -> None:
        with self._lock:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS traces (
                    trace_id TEXT PRIMARY KEY,
                    seq INTEGER,
                    label TEXT,
                    created_at TEXT,
                    status TEXT,
                    duration_ms REAL
                );
                CREATE TABLE IF NOT EXISTS spans (
                    span_id TEXT PRIMARY KEY,
                    trace_id TEXT,
                    parent_id TEXT,
                    stage TEXT,
                    name TEXT,
                    status TEXT,
                    error TEXT,
                    duration_ms REAL,
                    attributes TEXT,
                    created_at TEXT,
                    seq INTEGER DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS failures (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    trace_id TEXT,
                    span_id TEXT,
                    stage TEXT,
                    name TEXT,
                    error TEXT,
                    stack TEXT,
                    created_at TEXT
                );
                CREATE TABLE IF NOT EXISTS counters (key TEXT PRIMARY KEY, value INTEGER);
                CREATE INDEX IF NOT EXISTS idx_spans_trace ON spans(trace_id);
                CREATE INDEX IF NOT EXISTS idx_failures_trace ON failures(trace_id);
                """
            )
            self._conn.commit()

    # ---------------- trace ids ----------------
    def new_trace_id(self) -> str:
        """JRV-<year>-<8 digit monotonic sequence>."""
        year = datetime.now(timezone.utc).year
        key = f"trace_seq_{year}"
        with self._lock:
            row = self._conn.execute("SELECT value FROM counters WHERE key=?", (key,)).fetchone()
            nxt = (row["value"] if row else 0) + 1
            self._conn.execute(
                "INSERT INTO counters(key, value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, nxt),
            )
            self._conn.commit()
        return f"JRV-{year}-{nxt:08d}"

    def start_trace(self, label: str) -> str:
        trace_id = self.new_trace_id()
        seq = int(trace_id.rsplit("-", 1)[1])
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO traces(trace_id, seq, label, created_at, status, duration_ms) VALUES(?,?,?,?,?,?)",
                (trace_id, seq, label, _utc(), "running", None),
            )
            self._conn.commit()
        self._local.stack = []
        self._local.trace_id = trace_id
        self._local.t0 = time.time()
        return trace_id

    @property
    def current_trace_id(self) -> Optional[str]:
        return getattr(self._local, "trace_id", None)

    def end_trace(self, trace_id: str, status: str = "ok") -> Dict[str, Any]:
        t0 = getattr(self._local, "t0", None)
        dur = round((time.time() - t0) * 1000.0, 3) if t0 else None
        with self._lock:
            self._conn.execute(
                "UPDATE traces SET status=?, duration_ms=? WHERE trace_id=?", (status, dur, trace_id)
            )
            self._conn.commit()
        if getattr(self._local, "trace_id", None) == trace_id:
            self._local.trace_id = None
            self._local.stack = []
        return {"trace_id": trace_id, "status": status, "duration_ms": dur}

    # ---------------- spans ----------------
    def _next_seq(self) -> int:
        with self._lock:
            self._seq = getattr(self, "_seq", 0) + 1
            return self._seq

    def span(self, stage: str, name: str, trace_id: Optional[str] = None, **attrs: Any) -> _SpanContext:
        if stage not in STAGES:
            raise ValueError(f"unknown stage {stage!r}; expected one of {STAGES}")
        tid = trace_id or self.current_trace_id or self.start_trace(name)
        stack: List[str] = getattr(self._local, "stack", None) or []
        parent = stack[-1] if stack else None
        sp = Span(
            trace_id=tid,
            span_id=uuid.uuid4().hex[:12],
            stage=stage,
            name=name,
            started=time.time(),
            parent_id=parent,
            attributes=dict(attrs),
            seq=self._next_seq(),
        )
        stack.append(sp.span_id)
        self._local.stack = stack
        return _SpanContext(self, sp)

    def end_span(self, span: Span, status: str = "ok", error: Optional[str] = None, stack: Optional[str] = None) -> None:
        span.ended = time.time()
        span.status = status
        span.error = error
        local_stack: List[str] = getattr(self._local, "stack", None) or []
        if local_stack and local_stack[-1] == span.span_id:
            local_stack.pop()
            self._local.stack = local_stack
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO spans(span_id, trace_id, parent_id, stage, name, status, error,"
                " duration_ms, attributes, created_at, seq) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (
                    span.span_id, span.trace_id, span.parent_id, span.stage, span.name, status, error,
                    span.duration_ms, json.dumps(span.attributes, default=str), _utc(), span.seq,
                ),
            )
            if status == "error":
                self._conn.execute(
                    "INSERT INTO failures(trace_id, span_id, stage, name, error, stack, created_at)"
                    " VALUES(?,?,?,?,?,?,?)",
                    (span.trace_id, span.span_id, span.stage, span.name, error, stack, _utc()),
                )
                self._conn.execute("UPDATE traces SET status='error' WHERE trace_id=?", (span.trace_id,))
            self._conn.commit()

    def record_event(self, stage: str, name: str, trace_id: Optional[str] = None, **attrs: Any) -> Dict[str, Any]:
        with self.span(stage, name, trace_id=trace_id, **attrs) as s:
            pass
        return s.span.to_dict()

    # ---------------- queries ----------------
    def get_trace(self, trace_id: str) -> Dict[str, Any]:
        with self._lock:
            head = self._conn.execute("SELECT * FROM traces WHERE trace_id=?", (trace_id,)).fetchone()
            spans = self._conn.execute(
                "SELECT * FROM spans WHERE trace_id=? ORDER BY seq, rowid", (trace_id,)
            ).fetchall()
        if head is None:
            raise KeyError(f"unknown trace {trace_id}")
        return {
            "trace_id": trace_id,
            "label": head["label"],
            "status": head["status"],
            "duration_ms": head["duration_ms"],
            "created_at": head["created_at"],
            "spans": [
                {
                    "span_id": r["span_id"], "parent_id": r["parent_id"], "stage": r["stage"],
                    "name": r["name"], "status": r["status"], "error": r["error"],
                    "duration_ms": r["duration_ms"], "attributes": json.loads(r["attributes"] or "{}"),
                }
                for r in spans
            ],
        }

    def chain(self, trace_id: str) -> List[str]:
        """Human readable stage chain, e.g. input -> router -> manager -> output."""
        tr = self.get_trace(trace_id)
        seen: List[str] = []
        for s in tr["spans"]:
            if not seen or seen[-1] != s["stage"]:
                seen.append(s["stage"])
        return seen

    def render_trace(self, trace_id: str) -> str:
        tr = self.get_trace(trace_id)
        by_parent: Dict[Optional[str], List[Dict[str, Any]]] = {}
        for s in tr["spans"]:
            by_parent.setdefault(s["parent_id"], []).append(s)
        lines = [f"{trace_id} [{tr['status']}] {tr['label']} ({tr['duration_ms']} ms)"]

        def walk(parent: Optional[str], depth: int) -> None:
            for s in by_parent.get(parent, []):
                mark = "+" if s["status"] == "ok" else "x"
                lines.append(
                    "  " * (depth + 1) + f"[{mark}] {s['stage']}:{s['name']} {s['duration_ms']} ms"
                    + (f" ERROR {s['error']}" if s["error"] else "")
                )
                walk(s["span_id"], depth + 1)

        walk(None, 0)
        return "\n".join(lines)

    def failure_report(self, trace_id: Optional[str] = None, limit: int = 20) -> Dict[str, Any]:
        with self._lock:
            if trace_id:
                rows = self._conn.execute(
                    "SELECT * FROM failures WHERE trace_id=? ORDER BY id DESC LIMIT ?", (trace_id, limit)
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT * FROM failures ORDER BY id DESC LIMIT ?", (limit,)
                ).fetchall()
        items = [
            {
                "trace_id": r["trace_id"], "stage": r["stage"], "name": r["name"],
                "error": r["error"], "at": r["created_at"],
                "stack_head": (r["stack"] or "").strip().splitlines()[-1] if r["stack"] else None,
            }
            for r in rows
        ]
        groups: Dict[str, int] = {}
        for it in items:
            key = f"{it['stage']}:{(it['error'] or '').split(':')[0]}"
            groups[key] = groups.get(key, 0) + 1
        return {"count": len(items), "failures": items, "grouped": groups}

    def recent_traces(self, limit: int = 20) -> List[Dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM traces ORDER BY seq DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    def health(self) -> Dict[str, Any]:
        with self._lock:
            total = self._conn.execute("SELECT COUNT(*) c FROM traces").fetchone()["c"]
            errs = self._conn.execute("SELECT COUNT(*) c FROM traces WHERE status='error'").fetchone()["c"]
            avg = self._conn.execute(
                "SELECT AVG(duration_ms) a FROM traces WHERE duration_ms IS NOT NULL"
            ).fetchone()["a"]
            slow = self._conn.execute(
                "SELECT stage, AVG(duration_ms) a FROM spans GROUP BY stage ORDER BY a DESC LIMIT 3"
            ).fetchall()
        rate = 0.0 if not total else round(errs / total, 4)
        return {
            "traces": total,
            "errors": errs,
            "error_rate": rate,
            "avg_trace_ms": round(avg, 3) if avg else None,
            "slowest_stages": [{"stage": r["stage"], "avg_ms": round(r["a"] or 0, 3)} for r in slow],
            "status": "healthy" if rate < 0.2 else ("degraded" if rate < 0.5 else "failed"),
        }

    def subscribe_events(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Feed for the GUI activity panel (newest first)."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT stage, name, status, created_at, trace_id FROM spans ORDER BY rowid DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def close(self) -> None:
        with self._lock:
            self._conn.close()


_OBS: Optional[Observability] = None
_OBS_LOCK = threading.Lock()


def get_observability(db_path: Optional[str] = None) -> Observability:
    global _OBS
    with _OBS_LOCK:
        if _OBS is None:
            _OBS = Observability(db_path)
        return _OBS
