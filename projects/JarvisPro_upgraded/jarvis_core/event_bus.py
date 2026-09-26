"""S29 Event Bus — non-blocking in-process publish/subscribe.

All real runtime lifecycle events pass through here so subsystems can
subscribe without coupling to each other.  Uses a background daemon thread
for async handlers; sync handlers run inline.
"""
from __future__ import annotations

import atexit
import json
import logging
import os
import sqlite3
import threading
import time
import traceback
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ----------------------------------------------------------------------------
# Event types — extend as needed
# ----------------------------------------------------------------------------
class EventType:
    # Lifecycle
    KERNEL_STARTING = "kernel:starting"
    KERNEL_READY = "kernel:ready"
    KERNEL_SHUTDOWN = "kernel:shutdown"

    # Manager lifecycle
    MANAGER_REGISTERED = "manager:registered"
    MANAGER_HEALTHY = "manager:healthy"
    MANAGER_DEGRADED = "manager:degraded"
    MANAGER_FAILED = "manager:failed"
    MANAGER_TASK_START = "manager:task_start"
    MANAGER_TASK_END = "manager:task_end"

    # Task lifecycle
    TASK_CREATED = "task:created"
    TASK_QUEUED = "task:queued"
    TASK_RUNNING = "task:running"
    TASK_COMPLETED = "task:completed"
    TASK_FAILED = "task:failed"
    TASK_CANCELLED = "task:cancelled"

    # Goal lifecycle
    GOAL_CREATED = "goal:created"
    GOAL_UPDATED = "goal:updated"
    GOAL_COMPLETED = "goal:completed"
    MILESTONE_COMPLETED = "milestone:completed"
    MILESTONE_TASK_CREATED = "milestone:task_created"

    # Security
    SECURITY_EVENT = "security:event"
    POLICY_ASK = "policy:ask"
    PERMISSION_GRANTED = "permission:granted"
    PERMISSION_DENIED = "permission:denied"

    # Memory / learning
    MEMORY_CAPTURED = "memory:captured"
    EXPERIENCE_LEARNED = "experience:learned"

    # Self-improvement
    IMPROVEMENT_APPLIED = "improvement:applied"
    IMPROVEMENT_ROLLBACK = "improvement:rollback"

    # Background tasks
    BACKGROUND_JOB_START = "background:job_start"
    BACKGROUND_JOB_END = "background:job_end"

    # Browser / automation
    BROWSER_OPENED = "browser:opened"
    AUTOMATION_EXECUTED = "automation:executed"

    # API
    API_REQUEST = "api:request"

    # Catch-all
    ANY = "*"


# ----------------------------------------------------------------------------
# Event dataclass
# ----------------------------------------------------------------------------
@dataclass
class Event:
    event_type: str
    data: Dict[str, Any] = field(default_factory=dict)
    source: str = "unknown"
    trace_id: Optional[str] = None
    event_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    timestamp: str = field(default_factory=_utc)
    correlation_id: Optional[str] = None  # links related events

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "source": self.source,
            "trace_id": self.trace_id,
            "timestamp": self.timestamp,
            "correlation_id": self.correlation_id,
            "data": self.data,
        }


# ----------------------------------------------------------------------------
# Subscription
# ----------------------------------------------------------------------------
@dataclass
class Subscription:
    event_type: str  # exact type or EventType.ANY
    handler: Callable[[Event], Any]
    async_handler: bool = False  # if True, run in background thread pool
    description: str = ""

    def matches(self, event_type: str) -> bool:
        return self.event_type in (event_type, EventType.ANY)


# ----------------------------------------------------------------------------
# Event Bus
# ----------------------------------------------------------------------------
class EventBus:
    """Thread-safe in-process event bus with history and async handler support."""

    DEFAULT_HISTORY = 500  # keep last 500 events in memory

    def __init__(self, db_path: Optional[str] = None, history_limit: int = DEFAULT_HISTORY):
        self._subs: Dict[str, List[Subscription]] = {}   # event_type -> subscriptions
        self._any_subs: List[Subscription] = []        # wildcard subscribers
        self._history: List[Event] = []
        self._history_limit = history_limit
        self._lock = threading.RLock()
        self._bg_queue: List[Event] = []
        self._bg_lock = threading.Lock()
        self._bg_event = threading.Event()
        self._bg_thread: Optional[threading.Thread] = None
        self._bg_running = False
        self._started = False

        # Optional persistent history
        if db_path:
            self._db_path = db_path
            self._ensure_db()
        else:
            self._db_path = None

    # ---- persistence ----
    def _ensure_db(self) -> None:
        """Create the events table if it doesn't exist. Idempotent and thread-safe."""
        if not self._db_path:
            return
        parent = os.path.dirname(self._db_path) or "."
        try:
            os.makedirs(parent, exist_ok=True)
        except PermissionError:
            logger.error("EventBus cannot create data directory %s — falling back to in-memory", parent)
            self._db_path = None
            return
        except OSError as exc:
            logger.warning("EventBus cannot create data directory %s: %s", parent, exc)
            self._db_path = None
            return

        # Use a dedicated connection with WAL for better concurrency.
        # check_same_thread=False + timeout allows bg thread to write while
        # the main thread is dispatching.
        try:
            conn = sqlite3.connect(self._db_path, timeout=10.0, isolation_level="DEFERRED")
            # Spin until the table exists, up to 3 attempts.
            # This handles a rare race where two processes init the same DB
            # concurrently — the winner creates the table; the loser retries.
            created = False
            for _ in range(3):
                try:
                    conn.execute(
                        """CREATE TABLE IF NOT EXISTS events (
                            id          INTEGER PRIMARY KEY AUTOINCREMENT,
                            event_id    TEXT UNIQUE,
                            event_type  TEXT,
                            source      TEXT,
                            trace_id    TEXT,
                            timestamp   TEXT,
                            correlation_id TEXT,
                            data        TEXT
                        )"""
                    )
                    conn.execute("CREATE INDEX IF NOT EXISTS idx_et ON events(event_type)")
                    conn.execute("CREATE INDEX IF NOT EXISTS idx_ts ON events(timestamp)")
                    conn.commit()
                    created = True
                    break
                except sqlite3.OperationalError as e:
                    # "table events already exists" — not an error
                    if "already exists" in str(e):
                        created = True
                        break
                    # Something else (e.g. database locked) — retry
                    conn.rollback()
                    import time; time.sleep(0.1)
            conn.close()

            if not created:
                logger.error(
                    "EventBus DB init failed after 3 retries at %s — "
                    "falling back to in-memory. Events will not be persisted.",
                    self._db_path
                )
                self._db_path = None
        except Exception as exc:
            logger.error("EventBus DB init failed (unexpected): %s — falling back to in-memory", exc)
            self._db_path = None

    def _persist(self, event: Event) -> None:
        """Write one event to the SQLite DB. Safe to call from any thread."""
        if not self._db_path:
            return
        try:
            # Each persist gets its own connection (no shared state across threads).
            # isolation_level="DEFERRED" avoids locking overhead.
            conn = sqlite3.connect(self._db_path, timeout=5.0, isolation_level="DEFERRED")
            try:
                conn.execute(
                    "INSERT OR IGNORE INTO events VALUES(NULL,?,?,?,?,?,?,?)",
                    (event.event_id, event.event_type, event.source, event.trace_id,
                     event.timestamp, event.correlation_id,
                     json.dumps(event.data, default=str)),
                )
                conn.commit()
            finally:
                conn.close()
        except sqlite3.OperationalError as exc:
            # Only log real persistence errors (not "db_path is None" which returns early)
            if "no such table" in str(exc) or "database is locked" in str(exc):
                logger.error(
                    "EventBus persist error on %s: %s — falling back to in-memory",
                    self._db_path, exc
                )
                self._db_path = None
            else:
                logger.warning("EventBus persist failed: %s", exc)
        except Exception as exc:
            logger.warning("EventBus persist failed: %s", exc)

    # ---- background async handler thread ----
    def _start_bg(self) -> None:
        with self._bg_lock:
            if self._bg_running:
                return
            self._bg_running = True
            self._bg_thread = threading.Thread(target=self._bg_worker, daemon=True,
                                                name="EventBus-bg")
            self._bg_thread.start()

    def _bg_worker(self) -> None:
        """Background daemon that drains the async handler queue."""
        while self._bg_running:
            self._bg_event.wait(timeout=5.0)
            if not self._bg_running:
                break
            self._bg_event.clear()
            to_dispatch: List[Event] = []
            with self._bg_lock:
                to_dispatch = self._bg_queue
                self._bg_queue = []
            for ev in to_dispatch:
                # Invoke async handlers directly (sync ones already ran in publish())
                subs: List[Subscription] = []
                with self._lock:
                    subs += self._subs.get(ev.event_type, [])
                    subs += self._any_subs
                for sub in subs:
                    if not sub.async_handler:
                        continue
                    try:
                        sub.handler(ev)
                    except Exception as exc:
                        logger.error("EventBus async handler error [%s]: %s",
                                     sub.description or ev.event_type, exc)

    def _dispatch_async(self, event: Event) -> None:
        with self._bg_lock:
            self._bg_queue.append(event)
            self._bg_event.set()

    # ---- publish ----
    def publish(self, event: Event) -> None:
        """Main publish entry point.  Async handlers run in background."""
        if not self._started:
            self._start_bg()
            self._started = True

        # Record history
        with self._lock:
            self._history.append(event)
            if len(self._history) > self._history_limit:
                self._history = self._history[-self._history_limit:]

        # Persist
        self._persist(event)

        # Sync handlers inline
        self._dispatch_sync(event)

        # Async handlers via bg queue
        self._dispatch_async(event)

    def _dispatch_sync(self, event: Event) -> None:
        # Collect matching subs under lock
        subs: List[Subscription] = []
        with self._lock:
            subs += self._subs.get(event.event_type, [])
            subs += self._any_subs

        for sub in subs:
            if sub.async_handler:
                continue
            try:
                sub.handler(event)
            except Exception as exc:
                logger.error("EventBus handler error [%s]: %s", sub.description or event.event_type, exc)

    # ---- subscribe ----
    def subscribe(self, event_type: str, handler: Callable[[Event], Any],
                 async_handler: bool = False,
                 description: str = "") -> Subscription:
        sub = Subscription(event_type, handler, async_handler, description)
        with self._lock:
            if event_type == EventType.ANY:
                self._any_subs.append(sub)
            else:
                if event_type not in self._subs:
                    self._subs[event_type] = []
                self._subs[event_type].append(sub)
        return sub

    def unsubscribe(self, sub: Subscription) -> bool:
        with self._lock:
            if sub.event_type == EventType.ANY:
                try:
                    self._any_subs.remove(sub)
                    return True
                except ValueError:
                    return False
            return sub in self._subs.get(sub.event_type, [])

    # ---- convenience publishers ----
    def emit(self, event_type: str, data: Optional[Dict[str, Any]] = None,
             source: str = "system", trace_id: Optional[str] = None,
             correlation_id: Optional[str] = None) -> Event:
        ev = Event(event_type, data or {}, source, trace_id, correlation_id=correlation_id)
        self.publish(ev)
        return ev

    # ---- queries ----
    def history(self, event_type: Optional[str] = None, limit: int = 100) -> List[Event]:
        with self._lock:
            if event_type:
                return [e for e in self._history if e.event_type == event_type][-limit:]
            return list(self._history)[-limit:]

    def recent(self, limit: int = 20) -> List[Dict[str, Any]]:
        return [e.to_dict() for e in self.history(limit=limit)][::-1]

    @property
    def subscriber_count(self) -> int:
        with self._lock:
            return sum(len(v) for v in self._subs.values()) + len(self._any_subs)

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            type_counts: Dict[str, int] = {}
            for e in self._history:
                type_counts[e.event_type] = type_counts.get(e.event_type, 0) + 1
            sub_count = sum(len(v) for v in self._subs.values()) + len(self._any_subs)
        return {
            "history_size": len(self._history),
            "history_limit": self._history_limit,
            "subscriptions": sub_count,
            "subscriber_count": sub_count,
            "event_types_seen": len(type_counts),
            "top_types": dict(sorted(type_counts.items(), key=lambda kv: -kv[1])[:10]),
            "persistence": {
                "db_path": self._db_path,
                "persist_enabled": self._db_path is not None,
            },
        }

    # ---- health check ----
    def health(self) -> Dict[str, Any]:
        """Verify persistence layer is healthy. Call this at kernel startup."""
        result = {
            "state": "ok",
            "db_path": self._db_path,
            "persistence_enabled": self._db_path is not None,
            "bg_thread_alive": False,
            "db_accessible": False,
            "table_exists": False,
            "error": None,
        }
        if self._bg_thread:
            result["bg_thread_alive"] = self._bg_thread.is_alive()

        if self._db_path:
            try:
                conn = sqlite3.connect(self._db_path, timeout=2.0, isolation_level="DEFERRED")
                conn.execute("SELECT 1 FROM events LIMIT 1").fetchone()
                conn.close()
                result["db_accessible"] = True
                result["table_exists"] = True
            except sqlite3.OperationalError as e:
                if "no such table" in str(e):
                    result["error"] = f"events table missing in {self._db_path}"
                    result["state"] = "degraded"
                else:
                    result["error"] = str(e)
                    result["state"] = "degraded"
            except Exception as e:
                result["error"] = str(e)
                result["state"] = "degraded"

        if self._db_path is None:
            result["state"] = "in_memory_only"

        return result

    # ---- load persisted events on restart ----
    def load_persisted(self, limit: int = 1000) -> int:
        """Load recent events from the DB into in-memory history on restart.

        Returns the number of events loaded. Call this at kernel startup,
        before publishing any new events.
        """
        if not self._db_path:
            return 0
        try:
            conn = sqlite3.connect(self._db_path, timeout=5.0, isolation_level="DEFERRED")
            try:
                rows = conn.execute(
                    "SELECT event_id, event_type, source, trace_id, timestamp, "
                    "correlation_id, data FROM events ORDER BY id ASC LIMIT ?",
                    (limit,)
                ).fetchall()
            finally:
                conn.close()

            loaded = 0
            with self._lock:
                for row in rows:
                    ev = Event(
                        event_type=row[1],
                        data=json.loads(row[6]) if row[6] else {},
                        source=row[2] or "unknown",
                        trace_id=row[3],
                        event_id=row[0],
                        timestamp=row[4],
                        correlation_id=row[5],
                    )
                    # Avoid duplicates if load_persisted is called twice
                    if not any(e.event_id == ev.event_id for e in self._history):
                        self._history.append(ev)
                        loaded += 1

                # Trim history to limit
                if len(self._history) > self._history_limit:
                    self._history = self._history[-self._history_limit:]

            logger.info("EventBus loaded %d persisted events from %s", loaded, self._db_path)
            return loaded
        except Exception as exc:
            logger.warning("EventBus load_persisted failed: %s", exc)
            return 0

    # ---- shutdown ----
    def shutdown(self) -> None:
        """Gracefully stop the event bus. Safe to call multiple times."""
        was_running = self._bg_running
        self._bg_running = False
        self._bg_event.set()
        if self._bg_thread and self._bg_thread.is_alive():
            self._bg_thread.join(timeout=3.0)
        # Emit shutdown event only if we were actually running.
        # Don't call self.emit() here — it would trigger _start_bg() again.
        if was_running:
            shutdown_ev = Event(
                EventType.KERNEL_SHUTDOWN,
                {"reason": "shutdown"},
                source="eventbus",
            )
            # Dispatch sync handlers for shutdown (but skip async to avoid race)
            self._dispatch_sync(shutdown_ev)
            with self._lock:
                self._history.append(shutdown_ev)
                if len(self._history) > self._history_limit:
                    self._history = self._history[-self._history_limit:]


# ----------------------------------------------------------------------------
# Global singleton
# ----------------------------------------------------------------------------
_bus: Optional[EventBus] = None
_bus_lock = threading.Lock()


def get_event_bus(db_path: Optional[str] = None) -> EventBus:
    global _bus
    with _bus_lock:
        if _bus is None:
            _bus = EventBus(db_path)
    return _bus


# Register cleanup
def _cleanup() -> None:
    global _bus
    if _bus is not None:
        try:
            _bus.shutdown()
        except Exception:
            pass
        _bus = None


atexit.register(_cleanup)
