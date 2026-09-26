"""Section 8 - reminder manager, scheduler and event engine.

Real behaviour implemented here:

* recurrence: ``once``, ``daily``, ``weekly``, ``monthly``, ``custom`` (every N
  minutes/hours/days) with real next-occurrence arithmetic;
* snooze with a bounded number of snoozes;
* an event engine (``tick``) that fires due reminders through registered
  delivery channels and records every attempt;
* retry with bounded attempts and backoff - never an infinite loop;
* escalation to a higher channel only when permitted by the user's preferences
  and limits;
* SQLite persistence, so reminders survive a restart (proved by the test
  reopening the database).

Storage: ``data/reminders.db``.
"""
from __future__ import annotations

import calendar
import json
import os
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Sequence

_DEF_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")

RECURRENCES = ("once", "daily", "weekly", "monthly", "custom")
STATES = ("scheduled", "snoozed", "fired", "failed", "escalated", "cancelled", "completed")

MAX_ATTEMPTS = 3
MAX_SNOOZES = 5
RETRY_BACKOFF_SECONDS = (30, 120, 600)
ESCALATION_CHAIN = ("desktop", "voice", "android", "email")

_FMT = "%Y-%m-%dT%H:%M:%S"


class DeliveryError(Exception):
    """Raised by a channel when delivery genuinely failed."""


def _now() -> datetime:
    return datetime.now()


def _fmt(dt: datetime) -> str:
    return dt.strftime(_FMT)


def _parse(text: str) -> datetime:
    return datetime.strptime(text, _FMT)


def _add_months(dt: datetime, months: int) -> datetime:
    month_index = dt.month - 1 + months
    year = dt.year + month_index // 12
    month = month_index % 12 + 1
    day = min(dt.day, calendar.monthrange(year, month)[1])  # 31 Jan + 1 month -> 28/29 Feb
    return dt.replace(year=year, month=month, day=day)


@dataclass
class Reminder:
    reminder_id: str
    text: str
    due_at: str
    recurrence: str = "once"
    interval: int = 0
    unit: str = "minutes"
    weekdays: List[int] = field(default_factory=list)
    channel: str = "desktop"
    priority: int = 3
    state: str = "scheduled"
    attempts: int = 0
    snoozes: int = 0
    escalation_level: int = 0
    last_error: Optional[str] = None
    created_at: str = field(default_factory=lambda: _fmt(_now()))
    updated_at: str = field(default_factory=lambda: _fmt(_now()))

    def to_dict(self) -> Dict[str, Any]:
        data = dict(self.__dict__)
        data["weekdays"] = list(self.weekdays)
        return data


class ReminderManager:
    def __init__(self, db_path: Optional[str] = None, policy: Any = None,
                 profile: Any = None, analytics: Any = None) -> None:
        os.makedirs(_DEF_DIR, exist_ok=True)
        self.db_path = db_path or os.path.join(_DEF_DIR, "reminders.db")
        self.policy = policy
        self.profile = profile
        self.analytics = analytics
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._channels: Dict[str, Callable[[Reminder], Any]] = {}
        self._init_db()

    def _init_db(self) -> None:
        with self._lock:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS reminders (
                    reminder_id TEXT PRIMARY KEY, text TEXT, due_at TEXT, recurrence TEXT,
                    interval INTEGER, unit TEXT, weekdays TEXT, channel TEXT, priority INTEGER,
                    state TEXT, attempts INTEGER, snoozes INTEGER, escalation_level INTEGER,
                    last_error TEXT, created_at TEXT, updated_at TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_rem_due ON reminders(state, due_at);
                CREATE TABLE IF NOT EXISTS reminder_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    reminder_id TEXT, event TEXT, channel TEXT, ok INTEGER, detail TEXT,
                    created_at TEXT
                );
                CREATE TABLE IF NOT EXISTS reminder_prefs (
                    key TEXT PRIMARY KEY, value TEXT
                );
                """
            )
            self._conn.commit()

    # ---------------- channels ----------------
    def register_channel(self, name: str, handler: Callable[[Reminder], Any]) -> None:
        if not callable(handler):
            raise TypeError("channel handler must be callable")
        self._channels[name] = handler

    def channels(self) -> List[str]:
        return sorted(self._channels)

    # ---------------- preferences ----------------
    def set_preference(self, key: str, value: Any) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO reminder_prefs(key, value) VALUES(?,?)"
                " ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, json.dumps(value)))
            self._conn.commit()

    def preference(self, key: str, default: Any = None) -> Any:
        with self._lock:
            row = self._conn.execute("SELECT value FROM reminder_prefs WHERE key=?",
                                     (key,)).fetchone()
        if row is None:
            if self.profile is not None:
                try:
                    value = self.profile.get(f"reminders.{key}")
                except Exception:
                    value = None
                if value is not None:
                    return value
            return default
        return json.loads(row["value"])

    # ---------------- scheduling ----------------
    def _row_to_reminder(self, row: sqlite3.Row) -> Reminder:
        data = dict(row)
        data["weekdays"] = json.loads(data.get("weekdays") or "[]")
        return Reminder(**data)

    def _save(self, rem: Reminder) -> None:
        rem.updated_at = _fmt(_now())
        self._conn.execute(
            "INSERT INTO reminders(reminder_id, text, due_at, recurrence, interval, unit, weekdays,"
            " channel, priority, state, attempts, snoozes, escalation_level, last_error,"
            " created_at, updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
            " ON CONFLICT(reminder_id) DO UPDATE SET text=excluded.text, due_at=excluded.due_at,"
            " recurrence=excluded.recurrence, interval=excluded.interval, unit=excluded.unit,"
            " weekdays=excluded.weekdays, channel=excluded.channel, priority=excluded.priority,"
            " state=excluded.state, attempts=excluded.attempts, snoozes=excluded.snoozes,"
            " escalation_level=excluded.escalation_level, last_error=excluded.last_error,"
            " updated_at=excluded.updated_at",
            (rem.reminder_id, rem.text, rem.due_at, rem.recurrence, rem.interval, rem.unit,
             json.dumps(rem.weekdays), rem.channel, rem.priority, rem.state, rem.attempts,
             rem.snoozes, rem.escalation_level, rem.last_error, rem.created_at, rem.updated_at),
        )
        self._conn.commit()

    def _event(self, reminder_id: str, event: str, channel: str, ok: bool, detail: str = "") -> None:
        self._conn.execute(
            "INSERT INTO reminder_events(reminder_id, event, channel, ok, detail, created_at)"
            " VALUES(?,?,?,?,?,?)",
            (reminder_id, event, channel, int(ok), detail, _fmt(_now())))
        self._conn.commit()

    def schedule(self, text: str, due_at: Any, *, recurrence: str = "once", interval: int = 0,
                 unit: str = "minutes", weekdays: Sequence[int] = (), channel: str = "desktop",
                 priority: int = 3) -> Reminder:
        if not isinstance(text, str) or not text.strip():
            raise ValueError("reminder text must be a non-empty string")
        if recurrence not in RECURRENCES:
            raise ValueError(f"recurrence must be one of {RECURRENCES}")
        if recurrence == "custom":
            if interval <= 0:
                raise ValueError("custom recurrence requires interval > 0")
            if unit not in ("minutes", "hours", "days"):
                raise ValueError("custom unit must be minutes, hours or days")
        if recurrence == "weekly" and weekdays:
            if any(not 0 <= int(d) <= 6 for d in weekdays):
                raise ValueError("weekdays must be 0 (Mon) .. 6 (Sun)")
        if isinstance(due_at, datetime):
            due = _fmt(due_at)
        elif isinstance(due_at, str):
            due = _fmt(_parse(due_at))  # validates format
        else:
            raise TypeError("due_at must be a datetime or 'YYYY-MM-DDTHH:MM:SS' string")
        rem = Reminder(reminder_id="R-" + uuid.uuid4().hex[:10], text=text.strip(), due_at=due,
                       recurrence=recurrence, interval=int(interval), unit=unit,
                       weekdays=[int(d) for d in weekdays], channel=channel,
                       priority=int(priority))
        with self._lock:
            self._save(rem)
            self._event(rem.reminder_id, "scheduled", channel, True, f"due {due} ({recurrence})")
        return rem

    def get(self, reminder_id: str) -> Reminder:
        with self._lock:
            row = self._conn.execute("SELECT * FROM reminders WHERE reminder_id=?",
                                     (reminder_id,)).fetchone()
        if row is None:
            raise KeyError(f"unknown reminder {reminder_id}")
        return self._row_to_reminder(row)

    def list(self, state: Optional[str] = None, limit: int = 100) -> List[Reminder]:
        query = "SELECT * FROM reminders"
        params: List[Any] = []
        if state:
            if state not in STATES:
                raise ValueError(f"unknown state {state!r}")
            query += " WHERE state=?"
            params.append(state)
        query += " ORDER BY due_at LIMIT ?"
        params.append(limit)
        with self._lock:
            rows = self._conn.execute(query, params).fetchall()
        return [self._row_to_reminder(row) for row in rows]

    def due(self, now: Optional[datetime] = None) -> List[Reminder]:
        moment = _fmt(now or _now())
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM reminders WHERE state IN ('scheduled','snoozed','failed')"
                " AND due_at<=? ORDER BY priority, due_at", (moment,)).fetchall()
        return [self._row_to_reminder(row) for row in rows]

    def cancel(self, reminder_id: str, reason: str = "cancelled by user") -> Reminder:
        with self._lock:
            rem = self.get(reminder_id)
            if rem.state in ("cancelled", "completed"):
                return rem
            rem.state = "cancelled"
            rem.last_error = None
            self._save(rem)
            self._event(reminder_id, "cancelled", rem.channel, True, reason)
        return rem

    # ---------------- recurrence ----------------
    def next_occurrence(self, rem: Reminder, after: Optional[datetime] = None) -> Optional[datetime]:
        base = after or _parse(rem.due_at)
        if rem.recurrence == "once":
            return None
        if rem.recurrence == "daily":
            return base + timedelta(days=1)
        if rem.recurrence == "weekly":
            if not rem.weekdays:
                return base + timedelta(weeks=1)
            for offset in range(1, 8):
                candidate = base + timedelta(days=offset)
                if candidate.weekday() in rem.weekdays:
                    return candidate
            return base + timedelta(weeks=1)
        if rem.recurrence == "monthly":
            return _add_months(base, 1)
        if rem.recurrence == "custom":
            delta = {"minutes": timedelta(minutes=rem.interval),
                     "hours": timedelta(hours=rem.interval),
                     "days": timedelta(days=rem.interval)}[rem.unit]
            return base + delta
        return None

    # ---------------- snooze ----------------
    def snooze(self, reminder_id: str, minutes: int = 10) -> Reminder:
        if minutes <= 0:
            raise ValueError("snooze minutes must be positive")
        with self._lock:
            rem = self.get(reminder_id)
            if rem.state in ("cancelled", "completed"):
                raise ValueError(f"cannot snooze a {rem.state} reminder")
            limit = int(self.preference("max_snoozes", MAX_SNOOZES))
            if rem.snoozes >= limit:
                self._event(reminder_id, "snooze_refused", rem.channel, False,
                            f"snooze limit {limit} reached")
                raise ValueError(f"snooze limit reached ({limit}); reschedule instead")
            rem.snoozes += 1
            rem.state = "snoozed"
            rem.due_at = _fmt(_now() + timedelta(minutes=minutes))
            rem.attempts = 0
            self._save(rem)
            self._event(reminder_id, "snoozed", rem.channel, True,
                        f"+{minutes}m (snooze {rem.snoozes}/{limit})")
        return rem

    # ---------------- firing / retry / escalation ----------------
    def _deliver(self, rem: Reminder, channel: str) -> Dict[str, Any]:
        handler = self._channels.get(channel)
        if handler is None:
            return {"ok": False, "reason": f"channel {channel} unavailable", "status": "unavailable"}
        if self.policy is not None:
            try:
                decision = self.policy.check(f"notify.{channel}")
                allowed = decision if isinstance(decision, bool) else getattr(decision, "allowed", True)
                if not allowed:
                    return {"ok": False, "reason": f"policy denied notify.{channel}",
                            "status": "permission_denied"}
            except Exception as exc:  # policy must never break delivery silently
                self._event(rem.reminder_id, "policy_error", channel, False, repr(exc))
        try:
            handler(rem)
            return {"ok": True, "reason": "delivered", "status": "success"}
        except DeliveryError as exc:
            return {"ok": False, "reason": str(exc), "status": "failure"}
        except Exception as exc:
            return {"ok": False, "reason": f"{type(exc).__name__}: {exc}", "status": "failure"}

    def escalation_channel(self, rem: Reminder) -> Optional[str]:
        """Next permitted channel, honouring preferences, limits and availability."""
        if not bool(self.preference("allow_escalation", True)):
            return None
        max_level = int(self.preference("max_escalation_level", len(ESCALATION_CHAIN) - 1))
        chain = list(self.preference("escalation_chain", list(ESCALATION_CHAIN)))
        blocked = set(self.preference("blocked_channels", []))
        try:
            start = chain.index(rem.channel)
        except ValueError:
            start = -1
        for level in range(start + 1, min(len(chain), max_level + 1)):
            candidate = chain[level]
            if candidate in blocked or candidate not in self._channels:
                continue
            if self.profile is not None:
                try:
                    if self.profile.permission(f"notify.{candidate}") is False:
                        continue
                except Exception:
                    pass
            return candidate
        return None

    def fire(self, reminder_id: str) -> Dict[str, Any]:
        """Deliver one reminder, applying retry, escalation and recurrence."""
        with self._lock:
            rem = self.get(reminder_id)
            if rem.state in ("cancelled", "completed"):
                return {"reminder_id": reminder_id, "status": "skipped", "state": rem.state,
                        "reason": f"reminder already {rem.state}"}
            rem.attempts += 1
            result = self._deliver(rem, rem.channel)
            self._event(reminder_id, "delivery", rem.channel, result["ok"], result["reason"])

            if result["ok"]:
                rem.last_error = None
                rem.attempts = 0
                nxt = self.next_occurrence(rem, _now())
                if nxt is None:
                    rem.state = "completed"
                else:
                    rem.state = "scheduled"
                    rem.due_at = _fmt(nxt)
                    rem.snoozes = 0
                    rem.escalation_level = 0
                self._save(rem)
                if self.analytics is not None:
                    try:
                        self.analytics.record("reminder", rem.text[:60], True)
                    except Exception:
                        pass
                return {"reminder_id": reminder_id, "status": "delivered", "state": rem.state,
                        "channel": rem.channel, "next_due": rem.due_at if nxt else None}

            rem.last_error = result["reason"]
            max_attempts = int(self.preference("max_attempts", MAX_ATTEMPTS))
            if rem.attempts < max_attempts:
                backoff = RETRY_BACKOFF_SECONDS[min(rem.attempts - 1,
                                                    len(RETRY_BACKOFF_SECONDS) - 1)]
                rem.state = "failed"  # retryable
                rem.due_at = _fmt(_now() + timedelta(seconds=backoff))
                self._save(rem)
                self._event(reminder_id, "retry_scheduled", rem.channel, False,
                            f"attempt {rem.attempts}/{max_attempts}, retry in {backoff}s")
                return {"reminder_id": reminder_id, "status": "retry_scheduled",
                        "state": rem.state, "attempt": rem.attempts, "retry_in_s": backoff,
                        "reason": result["reason"]}

            # attempts exhausted -> try escalation once per level
            target = self.escalation_channel(rem)
            if target is None:
                rem.state = "failed"
                self._save(rem)
                self._event(reminder_id, "gave_up", rem.channel, False,
                            f"no escalation available after {rem.attempts} attempts")
                if self.analytics is not None:
                    try:
                        self.analytics.record("reminder", rem.text[:60], False,
                                              metadata={"error": result["reason"]})
                    except Exception:
                        pass
                return {"reminder_id": reminder_id, "status": "failed", "state": rem.state,
                        "reason": f"delivery failed after {rem.attempts} attempts:"
                                  f" {result['reason']}", "escalated": False}
            escalated = self._deliver(rem, target)
            self._event(reminder_id, "escalation", target, escalated["ok"], escalated["reason"])
            rem.escalation_level += 1
            rem.channel = target
            rem.attempts = 0 if escalated["ok"] else rem.attempts
            if escalated["ok"]:
                nxt = self.next_occurrence(rem, _now())
                rem.state = "escalated" if nxt is None else "scheduled"
                if nxt is not None:
                    rem.due_at = _fmt(nxt)
            else:
                rem.state = "failed"
            self._save(rem)
            return {"reminder_id": reminder_id,
                    "status": "escalated" if escalated["ok"] else "failed",
                    "state": rem.state, "channel": target, "escalated": True,
                    "reason": escalated["reason"]}

    def tick(self, now: Optional[datetime] = None) -> List[Dict[str, Any]]:
        """Event engine step: fire everything currently due. Bounded work per call."""
        results = []
        for rem in self.due(now):
            results.append(self.fire(rem.reminder_id))
        return results

    def events(self, reminder_id: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        query = "SELECT * FROM reminder_events"
        params: List[Any] = []
        if reminder_id:
            query += " WHERE reminder_id=?"
            params.append(reminder_id)
        query += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        with self._lock:
            rows = self._conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            states = self._conn.execute(
                "SELECT state, COUNT(*) c FROM reminders GROUP BY state").fetchall()
            delivered = self._conn.execute(
                "SELECT COUNT(*) c FROM reminder_events WHERE event='delivery' AND ok=1"
            ).fetchone()["c"]
            failed = self._conn.execute(
                "SELECT COUNT(*) c FROM reminder_events WHERE event='delivery' AND ok=0"
            ).fetchone()["c"]
        return {"by_state": {row["state"]: row["c"] for row in states},
                "delivered": delivered, "failed_deliveries": failed}


_REMINDERS: Optional[ReminderManager] = None
_REM_LOCK = threading.RLock()


def get_reminder_manager(**kwargs: Any) -> ReminderManager:
    global _REMINDERS
    with _REM_LOCK:
        if _REMINDERS is None:
            _REMINDERS = ReminderManager(**kwargs)
        return _REMINDERS
