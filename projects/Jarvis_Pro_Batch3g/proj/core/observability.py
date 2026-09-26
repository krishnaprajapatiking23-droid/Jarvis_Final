"""
==========================================
JARVIS PRO
Observability - structured logs, traces, metrics
==========================================

Roadmap sections 32 (Analytics) and 39 (Observability & Diagnostics).

Adapted from the logging/telemetry patterns of Mark-LII and ULTRON, but
rebuilt on sqlite so the data survives restarts and the existing analytics
layer can query it.

Everything is best-effort: if the database cannot be opened, JARVIS keeps
working and the calls become no-ops.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from typing import Any, Iterator

try:
    from config import config

    _DB_PATH = str(config.data_path("observability.db"))

except Exception:  # pragma: no cover - defensive
    _DB_PATH = "data/observability.db"


_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at  REAL    NOT NULL,
    trace_id    TEXT    NOT NULL,
    level       TEXT    NOT NULL,
    source      TEXT    NOT NULL,
    message     TEXT    NOT NULL,
    payload     TEXT    NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS spans (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    trace_id    TEXT    NOT NULL,
    name        TEXT    NOT NULL,
    started_at  REAL    NOT NULL,
    duration    REAL,
    ok          INTEGER NOT NULL DEFAULT 1,
    error       TEXT    NOT NULL DEFAULT '',
    payload     TEXT    NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS events_trace ON events (trace_id);
CREATE INDEX IF NOT EXISTS spans_name   ON spans  (name);
"""


class Observability:

    def __init__(self, path: str = _DB_PATH) -> None:
        self.path = path
        self._lock = threading.RLock()
        self._local = threading.local()
        self._ready = False

    # ---------------------------------------------------- database

    def _connect(self) -> sqlite3.Connection | None:
        try:
            connection = sqlite3.connect(self.path, timeout=5)
            connection.row_factory = sqlite3.Row

            if not self._ready:
                connection.executescript(_SCHEMA)
                connection.commit()
                self._ready = True

            return connection

        except Exception:
            return None

    # ---------------------------------------------------- traces

    def trace_id(self) -> str:
        """Trace id for the current thread, created on first use."""

        current = getattr(self._local, "trace_id", "")

        if not current:
            current = uuid.uuid4().hex[:12]
            self._local.trace_id = current

        return current

    def new_trace(self, name: str = "") -> str:
        """Start a fresh trace - one per user command."""

        self._local.trace_id = uuid.uuid4().hex[:12]

        if name:
            self.log("info", "trace", f"trace started: {name}")

        return self._local.trace_id

    # ---------------------------------------------------- writing

    def log(
        self,
        level: str,
        source: str,
        message: str,
        **payload: Any,
    ) -> None:
        """Structured log line. Never raises."""

        with self._lock:
            connection = self._connect()

            if connection is None:
                return

            try:
                connection.execute(
                    "INSERT INTO events "
                    "(created_at, trace_id, level, source, message, payload) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        time.time(),
                        self.trace_id(),
                        str(level).lower(),
                        str(source),
                        str(message)[:2000],
                        json.dumps(payload, default=str)[:4000],
                    ),
                )
                connection.commit()

            except Exception:
                pass

            finally:
                connection.close()

    def info(self, source: str, message: str, **payload: Any) -> None:
        self.log("info", source, message, **payload)

    def warn(self, source: str, message: str, **payload: Any) -> None:
        self.log("warning", source, message, **payload)

    def error(self, source: str, message: str, **payload: Any) -> None:
        self.log("error", source, message, **payload)

    def record(
        self,
        name: str,
        duration: float,
        ok: bool = True,
        error: str = "",
        **payload: Any,
    ) -> None:
        """Store a finished span (a tool call, model call, task, ...)."""

        with self._lock:
            connection = self._connect()

            if connection is None:
                return

            try:
                connection.execute(
                    "INSERT INTO spans "
                    "(trace_id, name, started_at, duration, ok, error, payload) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        self.trace_id(),
                        str(name),
                        time.time() - max(duration, 0.0),
                        float(duration),
                        1 if ok else 0,
                        str(error)[:1000],
                        json.dumps(payload, default=str)[:4000],
                    ),
                )
                connection.commit()

            except Exception:
                pass

            finally:
                connection.close()

    @contextmanager
    def span(self, name: str, **payload: Any) -> Iterator[dict[str, Any]]:
        """Time a block of work and store the result.

            with observability.span("tool.open_app", app="chrome"):
                ...
        """

        started = time.time()
        state: dict[str, Any] = {"ok": True, "error": ""}

        try:
            yield state

        except Exception as error:
            state["ok"] = False
            state["error"] = f"{type(error).__name__}: {error}"

            self.record(
                name,
                time.time() - started,
                ok=False,
                error=state["error"],
                **payload,
            )

            raise

        else:
            self.record(
                name,
                time.time() - started,
                ok=bool(state.get("ok", True)),
                error=str(state.get("error", "")),
                **payload,
            )

    # ---------------------------------------------------- reading

    def stats(self, name: str = "") -> list[dict[str, Any]]:
        """Success rate and average duration per span name."""

        connection = self._connect()

        if connection is None:
            return []

        try:
            sql = (
                "SELECT name, COUNT(*) AS runs, "
                "SUM(ok) AS ok_runs, AVG(duration) AS avg_duration "
                "FROM spans "
            )
            params: tuple[Any, ...] = ()

            if name:
                sql += "WHERE name = ? "
                params = (name,)

            sql += "GROUP BY name ORDER BY runs DESC"

            rows = connection.execute(sql, params).fetchall()

            report = []

            for row in rows:
                runs = int(row["runs"] or 0)
                ok_runs = int(row["ok_runs"] or 0)

                report.append(
                    {
                        "name": row["name"],
                        "runs": runs,
                        "success": ok_runs,
                        "failed": runs - ok_runs,
                        "success_rate": round(ok_runs / runs, 3) if runs else 0.0,
                        "avg_duration": round(float(row["avg_duration"] or 0.0), 3),
                    }
                )

            return report

        except Exception:
            return []

        finally:
            connection.close()

    def recent(self, limit: int = 50, level: str = "") -> list[dict[str, Any]]:
        connection = self._connect()

        if connection is None:
            return []

        try:
            sql = "SELECT * FROM events "
            params: tuple[Any, ...] = ()

            if level:
                sql += "WHERE level = ? "
                params = (level.lower(),)

            sql += "ORDER BY id DESC LIMIT ?"
            params = params + (int(limit),)

            rows = connection.execute(sql, params).fetchall()

            return [dict(row) for row in rows]

        except Exception:
            return []

        finally:
            connection.close()

    def failures(self, limit: int = 20) -> list[dict[str, Any]]:
        """Latest failed spans - the input of the self-correction layer."""

        connection = self._connect()

        if connection is None:
            return []

        try:
            rows = connection.execute(
                "SELECT * FROM spans WHERE ok = 0 ORDER BY id DESC LIMIT ?",
                (int(limit),),
            ).fetchall()

            return [dict(row) for row in rows]

        except Exception:
            return []

        finally:
            connection.close()

    def health(self) -> dict[str, Any]:
        """One-call diagnostic summary for the dashboard."""

        spans = self.stats()

        runs = sum(item["runs"] for item in spans)
        ok = sum(item["success"] for item in spans)

        return {
            "database": self.path,
            "tracked_operations": len(spans),
            "total_runs": runs,
            "success_rate": round(ok / runs, 3) if runs else 0.0,
            "recent_errors": len(self.recent(limit=20, level="error")),
            "worst": sorted(spans, key=lambda item: item["success_rate"])[:5],
        }


observability = Observability()
