"""S9/S10/S17 Task kernel: unified task object, state machine, dependencies,
execution history, failure reasons, rollback, cancellation propagation,
persistent execution and crash recovery, resource-aware scheduling.
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
from typing import Any, Callable, Dict, List, Optional, Sequence

from .graph import CycleError, DependencyGraph

_DEF_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")

CREATED, QUEUED, RUNNING, PAUSED, COMPLETED, FAILED, CANCELLED, ROLLED_BACK = (
    "created", "queued", "running", "paused", "completed", "failed", "cancelled", "rolled_back",
)

VALID_TRANSITIONS: Dict[str, set] = {
    CREATED: {QUEUED, CANCELLED},
    QUEUED: {RUNNING, CANCELLED, PAUSED, FAILED},  # can fail pre-flight (unmet deps, no resources)
    RUNNING: {COMPLETED, FAILED, PAUSED, CANCELLED, QUEUED},  # QUEUED = re-queued by crash recovery
    PAUSED: {RUNNING, CANCELLED, QUEUED},
    FAILED: {QUEUED, ROLLED_BACK, CANCELLED},
    COMPLETED: {ROLLED_BACK},
    CANCELLED: set(),
    ROLLED_BACK: set(),
}

# Destructive actions are never auto-resumed after a crash.
DESTRUCTIVE_KINDS = {"delete", "format", "overwrite", "send", "payment", "shutdown", "install"}


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class StateError(RuntimeError):
    pass


@dataclass
class Task:
    title: str
    task_id: str = field(default_factory=lambda: "T-" + uuid.uuid4().hex[:10])
    kind: str = "generic"
    owner: str = "owner"
    manager: Optional[str] = None
    priority: int = 5              # 1 = highest
    state: str = CREATED
    parent_id: Optional[str] = None
    depends_on: List[str] = field(default_factory=list)
    payload: Dict[str, Any] = field(default_factory=dict)
    result: Optional[Any] = None
    failure_reason: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 2
    estimate_s: float = 1.0
    requires: Dict[str, float] = field(default_factory=dict)  # cpu/ram_mb/net
    verification: Optional[str] = None
    progress: float = 0.0
    created_at: str = field(default_factory=_utc)
    updated_at: str = field(default_factory=_utc)
    trace_id: Optional[str] = None
    resumable: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return dict(self.__dict__)

    @property
    def destructive(self) -> bool:
        return self.kind in DESTRUCTIVE_KINDS or bool(self.payload.get("destructive"))


class TaskStore:
    """Persistent task state so execution survives a crash."""

    def __init__(self, db_path: Optional[str] = None):
        os.makedirs(_DEF_DIR, exist_ok=True)
        self.db_path = db_path or os.path.join(_DEF_DIR, "tasks.db")
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    task_id TEXT PRIMARY KEY, data TEXT, state TEXT, updated_at TEXT
                );
                CREATE TABLE IF NOT EXISTS history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT, from_state TEXT,
                    to_state TEXT, note TEXT, at TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_hist_task ON history(task_id);
                """
            )
            self._conn.commit()

    def save(self, task: Task) -> None:
        task.updated_at = _utc()
        with self._lock:
            self._conn.execute(
                "INSERT INTO tasks(task_id, data, state, updated_at) VALUES(?,?,?,?)"
                " ON CONFLICT(task_id) DO UPDATE SET data=excluded.data, state=excluded.state,"
                " updated_at=excluded.updated_at",
                (task.task_id, json.dumps(task.to_dict(), default=str), task.state, task.updated_at),
            )
            self._conn.commit()

    def log(self, task_id: str, frm: str, to: str, note: str = "") -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO history(task_id, from_state, to_state, note, at) VALUES(?,?,?,?,?)",
                (task_id, frm, to, note, _utc()),
            )
            self._conn.commit()

    def load_all(self) -> List[Task]:
        with self._lock:
            rows = self._conn.execute("SELECT data FROM tasks").fetchall()
        out = []
        for r in rows:
            d = json.loads(r["data"])
            out.append(Task(**{k: v for k, v in d.items() if k in Task.__annotations__}))
        return out

    def history(self, task_id: str) -> List[Dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT from_state, to_state, note, at FROM history WHERE task_id=? ORDER BY id",
                (task_id,),
            ).fetchall()
        return [dict(r) for r in rows]


class TaskManager:
    """Task state machine + dependency-aware runner."""

    def __init__(self, store: Optional[TaskStore] = None, observability: Any = None,
                 resources: Any = None):
        self.store = store or TaskStore()
        self.obs = observability
        self.resources = resources
        self.graph = DependencyGraph()
        self.tasks: Dict[str, Task] = {}
        self._rollbacks: Dict[str, Callable[[Task], Any]] = {}
        self._cancel_events: Dict[str, threading.Event] = {}
        self._lock = threading.RLock()
        for t in self.store.load_all():
            self.tasks[t.task_id] = t
            self.graph.add_node(t.task_id, "task", t.title, t.estimate_s)
            self._cancel_events[t.task_id] = threading.Event()
        for t in list(self.tasks.values()):
            for dep in t.depends_on:
                if dep in self.tasks:
                    try:
                        self.graph.add_dependency(dep, t.task_id)
                    except CycleError:
                        pass

    # ---------------- CRUD ----------------
    def create(self, title: str, **kw: Any) -> Task:
        depends_on = list(kw.pop("depends_on", []) or [])
        task = Task(title=title, depends_on=depends_on, **kw)
        with self._lock:
            self.tasks[task.task_id] = task
            self.graph.add_node(task.task_id, "task", title, task.estimate_s)
            for dep in depends_on:
                if dep not in self.tasks:
                    raise KeyError(f"unknown dependency {dep}")
                self.graph.add_dependency(dep, task.task_id)  # raises CycleError on cycles
            if task.parent_id:
                if task.parent_id not in self.tasks:
                    raise KeyError(f"unknown parent {task.parent_id}")
            self._cancel_events[task.task_id] = threading.Event()
            self.store.save(task)
            self.store.log(task.task_id, "-", CREATED, "created")
        return task

    def get(self, task_id: str) -> Task:
        t = self.tasks.get(task_id)
        if t is None:
            raise KeyError(f"unknown task {task_id}")
        return t

    def subtask(self, parent_id: str, title: str, **kw: Any) -> Task:
        parent = self.get(parent_id)
        kw.setdefault("manager", parent.manager)
        return self.create(title, parent_id=parent_id, **kw)

    def children(self, task_id: str) -> List[Task]:
        return [t for t in self.tasks.values() if t.parent_id == task_id]

    def descendants(self, task_id: str) -> List[Task]:
        out: List[Task] = []
        stack = self.children(task_id)
        while stack:
            t = stack.pop()
            out.append(t)
            stack.extend(self.children(t.task_id))
        return out

    # ---------------- state machine ----------------
    def transition(self, task_id: str, to_state: str, note: str = "", **fields: Any) -> Task:
        with self._lock:
            task = self.get(task_id)
            if to_state not in VALID_TRANSITIONS:
                raise StateError(f"unknown state {to_state}")
            if to_state not in VALID_TRANSITIONS[task.state]:
                raise StateError(f"illegal transition {task.state} -> {to_state} for {task_id}")
            frm = task.state
            task.state = to_state
            for k, v in fields.items():
                setattr(task, k, v)
            self.store.save(task)
            self.store.log(task_id, frm, to_state, note)
        if self.obs is not None:
            try:
                self.obs.record_event("manager", f"task:{to_state}", task_id=task_id, title=task.title)
            except Exception:
                pass
        return task

    def ready_tasks(self) -> List[Task]:
        ready = []
        for t in self.tasks.values():
            if t.state not in (CREATED, QUEUED):
                continue
            if all(self.tasks[d].state == COMPLETED for d in t.depends_on if d in self.tasks):
                ready.append(t)
        return sorted(ready, key=lambda t: (t.priority, t.created_at))

    def waves(self) -> List[List[str]]:
        return self.graph.execution_waves()

    def plan_view(self) -> str:
        return self.graph.render_ascii("TASK PLAN")

    # ---------------- cancellation propagation (S1) ----------------
    def cancel(self, task_id: str, reason: str = "user cancelled") -> Dict[str, Any]:
        """Cancels the task, all descendants and all dependents."""
        affected: List[str] = []
        targets = [task_id]
        targets += [t.task_id for t in self.descendants(task_id)]
        targets += sorted(self.graph.descendants(task_id))
        seen = set()
        for tid in targets:
            if tid in seen or tid not in self.tasks:
                continue
            seen.add(tid)
            t = self.tasks[tid]
            ev = self._cancel_events.setdefault(tid, threading.Event())
            ev.set()
            if t.state in (CREATED, QUEUED, RUNNING, PAUSED):
                self.transition(tid, CANCELLED, reason, failure_reason=reason)
                affected.append(tid)
        return {"cancelled": affected, "count": len(affected), "reason": reason}

    def is_cancelled(self, task_id: str) -> bool:
        ev = self._cancel_events.get(task_id)
        return bool(ev and ev.is_set())

    def cancel_token(self, task_id: str) -> threading.Event:
        return self._cancel_events.setdefault(task_id, threading.Event())

    # ---------------- rollback (S9) ----------------
    def register_rollback(self, task_id: str, fn: Callable[[Task], Any]) -> None:
        self._rollbacks[task_id] = fn

    def rollback(self, task_id: str, reason: str = "") -> Dict[str, Any]:
        task = self.get(task_id)
        # children first (reverse order of completion)
        rolled: List[str] = []
        for child in sorted(self.descendants(task_id), key=lambda t: t.updated_at, reverse=True):
            if child.state in (COMPLETED, FAILED):
                res = self._do_rollback(child, reason)
                if res:
                    rolled.append(child.task_id)
        if self._do_rollback(task, reason):
            rolled.append(task_id)
        return {"rolled_back": rolled, "reason": reason}

    def _do_rollback(self, task: Task, reason: str) -> bool:
        fn = self._rollbacks.get(task.task_id)
        note = reason
        if fn is not None:
            try:
                fn(task)
            except Exception as exc:
                note = f"rollback handler failed: {exc}"
                self.store.log(task.task_id, task.state, task.state, note)
                return False
        if ROLLED_BACK in VALID_TRANSITIONS[task.state]:
            self.transition(task.task_id, ROLLED_BACK, note or "rolled back")
            return True
        return False

    # ---------------- execution ----------------
    def run(self, task_id: str, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Dict[str, Any]:
        """Executes with retry, failure reason capture and cancellation checks."""
        task = self.get(task_id)
        if task.state == CREATED:
            self.transition(task_id, QUEUED, "queued")
        unmet = [d for d in task.depends_on if self.tasks.get(d) and self.tasks[d].state != COMPLETED]
        if unmet:
            self.transition(task_id, FAILED, "unmet dependencies",
                            failure_reason=f"unmet dependencies: {unmet}")
            return {"ok": False, "error": f"unmet dependencies: {unmet}", "state": FAILED}
        if self.is_cancelled(task_id):
            return {"ok": False, "error": "cancelled", "state": task.state}
        if self.resources is not None and task.requires:
            wait = self.resources.admit(task.requires)
            if not wait.get("admitted", True):
                self.transition(task_id, QUEUED, f"deferred: {wait.get('reason')}")
                return {"ok": False, "deferred": True, "reason": wait.get("reason")}
        while True:
            self.transition(task_id, RUNNING, f"attempt {task.retry_count + 1}")
            t0 = time.time()
            try:
                result = fn(*args, **kwargs)
                self.transition(task_id, COMPLETED, "ok", result=result, progress=100.0,
                                failure_reason=None)
                return {"ok": True, "result": result, "state": COMPLETED,
                        "duration_s": round(time.time() - t0, 4)}
            except Exception as exc:
                reason = f"{type(exc).__name__}: {exc}"
                tb = traceback.format_exc(limit=3)
                task.retry_count += 1
                can_retry = task.retry_count <= task.max_retries and not task.destructive \
                    and not self.is_cancelled(task_id)
                self.transition(task_id, FAILED, reason, failure_reason=reason)
                self.store.log(task_id, FAILED, FAILED, tb.strip().splitlines()[-1])
                if not can_retry:
                    return {"ok": False, "error": reason, "state": FAILED,
                            "retries": task.retry_count, "traceback": tb}
                self.transition(task_id, QUEUED, "retrying")

    def pause(self, task_id: str) -> Task:
        return self.transition(task_id, PAUSED, "paused")

    def resume(self, task_id: str) -> Task:
        return self.transition(task_id, QUEUED, "resumed")

    def set_progress(self, task_id: str, pct: float, note: str = "") -> Task:
        with self._lock:
            t = self.get(task_id)
            t.progress = max(0.0, min(100.0, float(pct)))
            self.store.save(t)
        return t

    # ---------------- crash recovery (S10) ----------------
    def recover(self) -> Dict[str, Any]:
        """After restart: resumable non-destructive work is re-queued, destructive
        work is quarantined for explicit human decision."""
        resumed, quarantined, finalized = [], [], []
        for t in list(self.tasks.values()):
            if t.state == RUNNING:
                if t.destructive or not t.resumable:
                    self.transition(t.task_id, FAILED, "interrupted destructive task quarantined",
                                    failure_reason="interrupted by crash; needs human decision")
                    quarantined.append(t.task_id)
                else:
                    self.transition(t.task_id, QUEUED, "recovered after crash")
                    resumed.append(t.task_id)
            elif t.state == PAUSED:
                finalized.append(t.task_id)
        return {"resumed": resumed, "quarantined": quarantined, "paused": finalized}

    # ---------------- reporting ----------------
    def history(self, task_id: str) -> List[Dict[str, Any]]:
        return self.store.history(task_id)

    def summary(self) -> Dict[str, Any]:
        counts: Dict[str, int] = {}
        for t in self.tasks.values():
            counts[t.state] = counts.get(t.state, 0) + 1
        return {"total": len(self.tasks), "by_state": counts,
                "active": [t.to_dict() for t in self.tasks.values()
                           if t.state in (QUEUED, RUNNING, PAUSED)]}
