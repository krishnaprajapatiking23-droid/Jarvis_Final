"""Background / multi-agent runtime (Section 18).

Real bounded-autonomy agents:
  * agent identity (id, name, role, capabilities, resource limits)
  * task assignment through a bounded worker pool
  * shared context (a locked blackboard scoped per run)
  * agent-to-agent communication (persisted mailboxes)
  * result aggregation across agents
  * failure handling, timeouts, cancellation, resource limits
  * iteration budget so an agent can never loop forever

Everything runs on daemon threads from a fixed-size pool, so no unbounded
thread creation and no GUI blocking. State lives in SQLite `agents.db`
(tables `agent_runs`, `agent_messages`) so runs survive restart.
"""
from __future__ import annotations

import json
import os
import queue
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

_DEF_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")

STATUS_PENDING = "pending"
STATUS_RUNNING = "running"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"
STATUS_TIMEOUT = "timeout"
STATUS_CANCELLED = "cancelled"
STATUS_REJECTED = "rejected"

TERMINAL = {STATUS_COMPLETED, STATUS_FAILED, STATUS_TIMEOUT, STATUS_CANCELLED,
            STATUS_REJECTED}

DEFAULT_MAX_WORKERS = 4
DEFAULT_TIMEOUT = 30.0
DEFAULT_MAX_ITERATIONS = 25


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class CancelledError(RuntimeError):
    """Raised inside an agent body when its run was cancelled."""


@dataclass
class AgentIdentity:
    id: str
    name: str
    role: str
    capabilities: List[str]
    max_iterations: int = DEFAULT_MAX_ITERATIONS
    timeout: float = DEFAULT_TIMEOUT
    max_concurrent: int = 2

    def to_dict(self) -> Dict[str, Any]:
        return {"id": self.id, "name": self.name, "role": self.role,
                "capabilities": list(self.capabilities),
                "max_iterations": self.max_iterations, "timeout": self.timeout,
                "max_concurrent": self.max_concurrent}


class SharedContext:
    """Thread-safe blackboard shared by the agents of one run group."""

    def __init__(self, initial: Optional[Dict[str, Any]] = None):
        self._lock = threading.RLock()
        self._data: Dict[str, Any] = dict(initial or {})
        self._writes: List[Dict[str, Any]] = []

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            return self._data.get(key, default)

    def put(self, key: str, value: Any, author: str = "system") -> None:
        with self._lock:
            self._data[key] = value
            self._writes.append({"key": key, "author": author, "at": _utc()})

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return dict(self._data)

    def writes(self) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._writes)


class AgentHandle:
    """Live view of one assigned agent task."""

    def __init__(self, run_id: str, agent: AgentIdentity, task: Dict[str, Any],
                 context: SharedContext, runtime: "AgentRuntime"):
        self.run_id = run_id
        self.agent = agent
        self.task = task
        self.context = context
        self._runtime = runtime
        self._cancel = threading.Event()
        self._done = threading.Event()
        self.status = STATUS_PENDING
        self.result: Any = None
        self.error: Optional[str] = None
        self.iterations = 0
        self.started_at: Optional[str] = None
        self.finished_at: Optional[str] = None
        self.duration: float = 0.0

    # --- API used by the agent body ---
    @property
    def cancelled(self) -> bool:
        return self._cancel.is_set()

    def checkpoint(self) -> None:
        """Agent bodies call this between steps to honour cancellation and the
        iteration budget (bounded autonomy - no infinite loops)."""
        if self._cancel.is_set():
            raise CancelledError(f"run {self.run_id} cancelled")
        self.iterations += 1
        if self.iterations > self.agent.max_iterations:
            raise RuntimeError(
                f"iteration budget exhausted ({self.agent.max_iterations}) - "
                "agent stopped to prevent an unbounded loop")

    def send(self, to_agent: str, subject: str, body: Any = None) -> str:
        return self._runtime.send_message(self.run_id, self.agent.name, to_agent,
                                          subject, body)

    def inbox(self, consume: bool = True) -> List[Dict[str, Any]]:
        return self._runtime.inbox(self.agent.name, consume=consume)

    def cancel(self, reason: str = "cancelled by caller") -> None:
        self._cancel.set()
        self.error = self.error or reason

    def wait(self, timeout: Optional[float] = None) -> Dict[str, Any]:
        self._done.wait(timeout if timeout is not None else self.agent.timeout + 5)
        return self.to_dict()

    def to_dict(self) -> Dict[str, Any]:
        return {"run_id": self.run_id, "agent": self.agent.name,
                "role": self.agent.role, "task": self.task, "status": self.status,
                "result": self.result, "error": self.error,
                "iterations": self.iterations, "started_at": self.started_at,
                "finished_at": self.finished_at, "duration": round(self.duration, 4),
                "ok": self.status == STATUS_COMPLETED}


class AgentRuntime:
    """Registry + bounded worker pool + mailbox for background agents."""

    capability = "agents"

    def __init__(self, db_path: Optional[str] = None, kernel: Any = None,
                 max_workers: int = DEFAULT_MAX_WORKERS):
        self.kernel = kernel
        self.max_workers = max(1, int(max_workers))
        path = db_path or os.path.join(_DEF_DIR, "agents.db")
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS agent_runs(
                    run_id TEXT PRIMARY KEY, agent TEXT, role TEXT, task TEXT,
                    status TEXT, result TEXT, error TEXT, iterations INTEGER,
                    started_at TEXT, finished_at TEXT, duration REAL, group_id TEXT);
                CREATE TABLE IF NOT EXISTS agent_messages(
                    id TEXT PRIMARY KEY, run_id TEXT, sender TEXT, recipient TEXT,
                    subject TEXT, body TEXT, created_at TEXT, consumed INTEGER DEFAULT 0);
                CREATE INDEX IF NOT EXISTS idx_msg_recipient ON agent_messages(recipient, consumed);
                CREATE INDEX IF NOT EXISTS idx_runs_group ON agent_runs(group_id);
                """
            )
            self._conn.commit()
        self._agents: Dict[str, AgentIdentity] = {}
        self._bodies: Dict[str, Callable[[AgentHandle], Any]] = {}
        self._handles: Dict[str, AgentHandle] = {}
        self._active: Dict[str, int] = {}
        self._queue: "queue.Queue[Optional[AgentHandle]]" = queue.Queue()
        self._workers: List[threading.Thread] = []
        self._shutdown = threading.Event()
        self._start_workers()

    # ---------------- registry ----------------
    def register(self, name: str, body: Callable[[AgentHandle], Any], *,
                 role: str = "worker", capabilities: Optional[List[str]] = None,
                 max_iterations: int = DEFAULT_MAX_ITERATIONS,
                 timeout: float = DEFAULT_TIMEOUT,
                 max_concurrent: int = 2) -> AgentIdentity:
        if not isinstance(name, str) or not name.strip():
            raise ValueError("agent name must be a non-empty string")
        if not callable(body):
            raise ValueError("agent body must be callable")
        identity = AgentIdentity(id="AG-" + uuid.uuid4().hex[:8], name=name.strip(),
                                 role=role, capabilities=list(capabilities or []),
                                 max_iterations=max(1, int(max_iterations)),
                                 timeout=float(timeout),
                                 max_concurrent=max(1, int(max_concurrent)))
        with self._lock:
            self._agents[identity.name] = identity
            self._bodies[identity.name] = body
        return identity

    def agents(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [a.to_dict() for a in self._agents.values()]

    def agents_for(self, capability: str) -> List[str]:
        with self._lock:
            return [a.name for a in self._agents.values() if capability in a.capabilities]

    # ---------------- worker pool ----------------
    def _start_workers(self) -> None:
        for i in range(self.max_workers):
            t = threading.Thread(target=self._worker_loop, name=f"jarvis-agent-{i}",
                                 daemon=True)
            t.start()
            self._workers.append(t)

    def _worker_loop(self) -> None:
        while not self._shutdown.is_set():
            try:
                handle = self._queue.get(timeout=0.2)
            except queue.Empty:
                continue
            if handle is None:
                self._queue.task_done()
                break
            try:
                self._execute(handle)
            finally:
                self._queue.task_done()

    def _execute(self, handle: AgentHandle) -> None:
        body = self._bodies.get(handle.agent.name)
        handle.status = STATUS_RUNNING
        handle.started_at = _utc()
        start = time.monotonic()
        result_box: Dict[str, Any] = {}

        def runner() -> None:
            try:
                result_box["value"] = body(handle)
            except CancelledError as exc:
                result_box["cancelled"] = str(exc)
            except Exception as exc:  # real failure handling, never swallowed
                result_box["error"] = f"{type(exc).__name__}: {exc}"

        thread = threading.Thread(target=runner, name=f"body-{handle.run_id}",
                                  daemon=True)
        thread.start()
        thread.join(handle.agent.timeout)
        handle.duration = time.monotonic() - start
        if thread.is_alive():
            # Cooperative cancellation: signal, give a grace period, then report
            # timeout. The daemon thread cannot block shutdown.
            handle._cancel.set()
            thread.join(min(2.0, handle.agent.timeout))
            handle.status = STATUS_TIMEOUT
            handle.error = f"agent exceeded its {handle.agent.timeout}s timeout"
        elif "cancelled" in result_box:
            handle.status = STATUS_CANCELLED
            handle.error = result_box["cancelled"]
        elif "error" in result_box:
            handle.status = STATUS_FAILED
            handle.error = result_box["error"]
        elif handle.cancelled:
            handle.status = STATUS_CANCELLED
            handle.error = handle.error or "cancelled"
        else:
            handle.status = STATUS_COMPLETED
            handle.result = result_box.get("value")
        handle.finished_at = _utc()
        with self._lock:
            self._active[handle.agent.name] = max(0, self._active.get(handle.agent.name, 1) - 1)
        self._persist(handle)
        handle._done.set()

    # ---------------- assignment ----------------
    def assign(self, agent_name: str, task: Dict[str, Any], *,
               context: Optional[SharedContext] = None,
               group_id: Optional[str] = None) -> AgentHandle:
        with self._lock:
            identity = self._agents.get(agent_name)
            if identity is None:
                raise KeyError(f"unknown agent {agent_name!r}")
            running = self._active.get(agent_name, 0)
            handle = AgentHandle("AR-" + uuid.uuid4().hex[:10], identity, dict(task or {}),
                                 context or SharedContext(), self)
            handle.group = group_id  # type: ignore[attr-defined]
            self._handles[handle.run_id] = handle
            if running >= identity.max_concurrent:
                handle.status = STATUS_REJECTED
                handle.error = (f"resource limit: {agent_name} already has {running} "
                                f"concurrent run(s) (max {identity.max_concurrent})")
                handle.finished_at = _utc()
                handle._done.set()
                self._persist(handle)
                return handle
            self._active[agent_name] = running + 1
        self._queue.put(handle)
        return handle

    def cancel(self, run_id: str, reason: str = "cancelled by user") -> Dict[str, Any]:
        with self._lock:
            handle = self._handles.get(run_id)
        if handle is None:
            return {"ok": False, "error": f"unknown run {run_id}"}
        if handle.status in TERMINAL:
            return {"ok": False, "error": f"run already {handle.status}",
                    "status": handle.status}
        handle.cancel(reason)
        return {"ok": True, "run_id": run_id, "status": "cancelling", "reason": reason}

    def cancel_group(self, group_id: str, reason: str = "group cancelled") -> Dict[str, Any]:
        cancelled = []
        with self._lock:
            handles = [h for h in self._handles.values()
                       if getattr(h, "group", None) == group_id]
        for handle in handles:
            if handle.status not in TERMINAL:
                handle.cancel(reason)
                cancelled.append(handle.run_id)
        return {"ok": True, "group": group_id, "cancelled": cancelled}

    # ---------------- multi-agent orchestration ----------------
    def run_group(self, assignments: List[Dict[str, Any]], *,
                  shared: Optional[Dict[str, Any]] = None,
                  timeout: Optional[float] = None) -> Dict[str, Any]:
        """Assign several agents against one shared context and aggregate.

        `assignments` = [{"agent": name, "task": {...}}, ...]
        """
        if not assignments:
            raise ValueError("assignments must be a non-empty list")
        group_id = "GRP-" + uuid.uuid4().hex[:8]
        context = SharedContext(shared)
        handles: List[AgentHandle] = []
        for spec in assignments:
            name = spec.get("agent")
            try:
                handles.append(self.assign(name, spec.get("task", {}),
                                           context=context, group_id=group_id))
            except KeyError as exc:
                stub = AgentHandle("AR-" + uuid.uuid4().hex[:10],
                                   AgentIdentity("AG-missing", str(name), "unknown", []),
                                   spec.get("task", {}), context, self)
                stub.status = STATUS_REJECTED
                stub.error = str(exc)
                stub._done.set()
                handles.append(stub)
        deadline = time.monotonic() + (timeout if timeout is not None else
                                       max(h.agent.timeout for h in handles) + 10)
        for handle in handles:
            remaining = max(0.05, deadline - time.monotonic())
            handle._done.wait(remaining)
        results = [h.to_dict() for h in handles]
        return self.aggregate(group_id, results, context)

    def aggregate(self, group_id: str, results: List[Dict[str, Any]],
                  context: Optional[SharedContext] = None) -> Dict[str, Any]:
        succeeded = [r for r in results if r["status"] == STATUS_COMPLETED]
        failed = [r for r in results if r["status"] not in (STATUS_COMPLETED,)]
        return {"group": group_id, "total": len(results),
                "succeeded": len(succeeded), "failed": len(failed),
                "ok": bool(succeeded) and not failed,
                "partial": bool(succeeded) and bool(failed),
                "results": results,
                "outputs": [r["result"] for r in succeeded],
                "errors": [{"agent": r["agent"], "status": r["status"],
                            "error": r["error"]} for r in failed],
                "shared_context": context.snapshot() if context else {}}

    # ---------------- messaging ----------------
    def send_message(self, run_id: Optional[str], sender: str, recipient: str,
                     subject: str, body: Any = None) -> str:
        msg_id = "MSG-" + uuid.uuid4().hex[:10]
        with self._lock:
            self._conn.execute(
                "INSERT INTO agent_messages(id, run_id, sender, recipient, subject,"
                " body, created_at, consumed) VALUES(?,?,?,?,?,?,?,0)",
                (msg_id, run_id, sender, recipient, subject,
                 json.dumps(body, default=str), _utc()))
            self._conn.commit()
        return msg_id

    def inbox(self, recipient: str, consume: bool = True,
              limit: int = 50) -> List[Dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM agent_messages WHERE recipient=? AND consumed=0"
                " ORDER BY created_at, id LIMIT ?", (recipient, int(limit))).fetchall()
            items = []
            for row in rows:
                item = dict(row)
                try:
                    item["body"] = json.loads(item["body"]) if item["body"] else None
                except json.JSONDecodeError:
                    pass
                items.append(item)
            if consume and items:
                self._conn.executemany(
                    "UPDATE agent_messages SET consumed=1 WHERE id=?",
                    [(i["id"],) for i in items])
                self._conn.commit()
        return items

    # ---------------- persistence / reporting ----------------
    def _persist(self, handle: AgentHandle) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO agent_runs(run_id, agent, role, task, status,"
                " result, error, iterations, started_at, finished_at, duration, group_id)"
                " VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (handle.run_id, handle.agent.name, handle.agent.role,
                 json.dumps(handle.task, default=str), handle.status,
                 json.dumps(handle.result, default=str), handle.error,
                 handle.iterations, handle.started_at, handle.finished_at,
                 handle.duration, getattr(handle, "group", None)))
            self._conn.commit()
        analytics = getattr(self.kernel, "analytics", None)
        if analytics is not None:
            try:
                analytics.record("agent", handle.agent.name,
                                 handle.status == STATUS_COMPLETED,
                                 duration=handle.duration, error=handle.error)
            except Exception:
                pass

    def runs(self, status: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        sql = "SELECT * FROM agent_runs"
        params: List[Any] = []
        if status:
            sql += " WHERE status=?"
            params.append(status)
        sql += " ORDER BY started_at DESC, run_id DESC LIMIT ?"
        params.append(int(limit))
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        out = []
        for row in rows:
            item = dict(row)
            for key in ("task", "result"):
                try:
                    item[key] = json.loads(item[key]) if item[key] else None
                except json.JSONDecodeError:
                    pass
            out.append(item)
        return out

    def active(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [h.to_dict() for h in self._handles.values()
                    if h.status not in TERMINAL]

    def health(self) -> Dict[str, Any]:
        with self._lock:
            registered = len(self._agents)
            busy = sum(self._active.values())
        return {"available": True, "registered_agents": registered,
                "workers": self.max_workers, "busy": busy,
                "queued": self._queue.qsize(),
                "live_threads": sum(1 for t in self._workers if t.is_alive())}

    def shutdown(self, timeout: float = 2.0) -> Dict[str, Any]:
        """Cancel live runs and stop workers - no thread leaks on exit."""
        with self._lock:
            live = [h for h in self._handles.values() if h.status not in TERMINAL]
        for handle in live:
            handle.cancel("runtime shutdown")
        self._shutdown.set()
        for _ in self._workers:
            self._queue.put(None)
        for t in self._workers:
            t.join(timeout)
        return {"ok": True, "cancelled": len(live),
                "workers_stopped": sum(1 for t in self._workers if not t.is_alive())}

    # ---------------- pipeline entry point ----------------
    def run(self, action: str, **kwargs: Any) -> Any:
        actions = {
            "assign": lambda: self.assign(kwargs["agent"], kwargs.get("task", {})).wait(),
            "run_group": lambda: self.run_group(kwargs["assignments"],
                                                shared=kwargs.get("shared"),
                                                timeout=kwargs.get("timeout")),
            "cancel": lambda: self.cancel(kwargs["run_id"],
                                          kwargs.get("reason", "cancelled by user")),
            "runs": lambda: self.runs(kwargs.get("status"), kwargs.get("limit", 50)),
            "agents": self.agents,
            "active": self.active,
            "health": self.health,
        }
        if action not in actions:
            return {"status": "invalid_input",
                    "error": f"unknown agent action {action!r}",
                    "available": sorted(actions)}
        return actions[action]()


__all__ = ["AgentRuntime", "AgentIdentity", "AgentHandle", "SharedContext",
           "CancelledError", "STATUS_COMPLETED", "STATUS_FAILED", "STATUS_TIMEOUT",
           "STATUS_CANCELLED", "STATUS_REJECTED", "TERMINAL"]
