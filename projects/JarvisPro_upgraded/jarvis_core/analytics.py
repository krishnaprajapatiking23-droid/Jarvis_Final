"""S32 Analytics + S17 resource-aware execution.

Event-sourced analytics: every execution event is appended to SQLite and all
rates/scores are computed from those real events (never hardcoded).
"""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

_DEF_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Analytics:
    def __init__(self, db_path: Optional[str] = None):
        os.makedirs(_DEF_DIR, exist_ok=True)
        self.db_path = db_path or os.path.join(_DEF_DIR, "analytics.db")
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    kind TEXT,         -- command | manager | tool | model | learning | improvement | recovery | prediction
                    name TEXT,
                    success INTEGER,
                    duration_ms REAL,
                    trace_id TEXT,
                    corrected INTEGER DEFAULT 0,
                    cost REAL DEFAULT 0,
                    meta TEXT,
                    at TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_ev_kind ON events(kind, name);
                """
            )
            self._conn.commit()

    # ---------------- recording ----------------
    def record(self, kind: str, name: str, success: bool = True, duration_ms: float = 0.0,
               trace_id: Optional[str] = None, corrected: bool = False, cost: float = 0.0,
               **meta: Any) -> Dict[str, Any]:
        row = (kind, name, 1 if success else 0, float(duration_ms), trace_id,
               1 if corrected else 0, float(cost), json.dumps(meta, default=str), _utc())
        with self._lock:
            self._conn.execute(
                "INSERT INTO events(kind,name,success,duration_ms,trace_id,corrected,cost,meta,at)"
                " VALUES(?,?,?,?,?,?,?,?,?)", row,
            )
            self._conn.commit()
        return {"kind": kind, "name": name, "success": success}

    def timer(self, kind: str, name: str, **meta: Any) -> "_Timer":
        return _Timer(self, kind, name, meta)

    # ---------------- aggregates ----------------
    def _rate(self, kind: Optional[str] = None) -> Dict[str, Any]:
        q = "SELECT COUNT(*) n, SUM(success) s, AVG(duration_ms) d FROM events"
        args: tuple = ()
        if kind:
            q += " WHERE kind=?"
            args = (kind,)
        with self._lock:
            r = self._conn.execute(q, args).fetchone()
        n = r["n"] or 0
        s = r["s"] or 0
        return {"total": n, "successes": s, "failures": n - s,
                "success_rate": round(s / n, 4) if n else None,
                "failure_rate": round((n - s) / n, 4) if n else None,
                "avg_ms": round(r["d"], 3) if r["d"] else None}

    def success_rate(self, kind: Optional[str] = None) -> Optional[float]:
        return self._rate(kind)["success_rate"]

    def failure_rate(self, kind: Optional[str] = None) -> Optional[float]:
        return self._rate(kind)["failure_rate"]

    def scores(self, kind: str, limit: int = 10) -> List[Dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT name, COUNT(*) n, SUM(success) s, AVG(duration_ms) d FROM events"
                " WHERE kind=? GROUP BY name ORDER BY n DESC LIMIT ?", (kind, limit),
            ).fetchall()
        out = []
        for r in rows:
            n, s = r["n"], r["s"] or 0
            out.append({"name": r["name"], "uses": n, "success_score": round(s / n, 4),
                        "avg_ms": round(r["d"] or 0, 3)})
        return out

    def most_used(self, kind: str = "command", limit: int = 5) -> List[Dict[str, Any]]:
        return self.scores(kind, limit)

    def manager_scores(self) -> List[Dict[str, Any]]:
        return self.scores("manager")

    def tool_scores(self) -> List[Dict[str, Any]]:
        return self.scores("tool")

    def model_scores(self) -> List[Dict[str, Any]]:
        return self.scores("model")

    def user_correction_rate(self) -> Optional[float]:
        with self._lock:
            r = self._conn.execute(
                "SELECT COUNT(*) n, SUM(corrected) c FROM events WHERE kind='command'"
            ).fetchone()
        return round((r["c"] or 0) / r["n"], 4) if r["n"] else None

    def learning_stats(self) -> Dict[str, Any]:
        return {"learning": self._rate("learning"), "improvement": self._rate("improvement"),
                "recovery_attempts": self._rate("recovery")["total"],
                "prediction_accuracy": self._rate("prediction")["success_rate"]}

    def ai_usage(self) -> Dict[str, Any]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT name, COUNT(*) n, AVG(duration_ms) d, SUM(cost) c FROM events"
                " WHERE kind='model' GROUP BY name"
            ).fetchall()
        return {r["name"]: {"calls": r["n"], "avg_latency_ms": round(r["d"] or 0, 2),
                            "cost": round(r["c"] or 0, 4)} for r in rows}

    def dashboard(self) -> Dict[str, Any]:
        return {
            "overall": self._rate(),
            "commands": self._rate("command"),
            "managers": self.manager_scores(),
            "tools": self.tool_scores(),
            "models": self.model_scores(),
            "ai_usage": self.ai_usage(),
            "learning": self.learning_stats(),
            "most_used_commands": self.most_used("command"),
            "user_correction_rate": self.user_correction_rate(),
            "generated_at": _utc(),
        }


class _Timer:
    def __init__(self, analytics: Analytics, kind: str, name: str, meta: Dict[str, Any]):
        self.a = analytics
        self.kind = kind
        self.name = name
        self.meta = meta
        self.t0 = 0.0

    def __enter__(self) -> "_Timer":
        self.t0 = time.time()
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        self.a.record(self.kind, self.name, success=exc is None,
                      duration_ms=(time.time() - self.t0) * 1000.0,
                      error=None if exc is None else str(exc), **self.meta)
        return False


# ----------------------------------------------------------------------------
# S17 resource-aware execution
# ----------------------------------------------------------------------------
class ResourceMonitor:
    """Real machine stats. Uses psutil when present, otherwise stdlib fallbacks
    (/proc on Linux, shutil for disk) and reports what it could not measure."""

    def __init__(self, cpu_limit: float = 90.0, ram_limit: float = 90.0):
        self.cpu_limit = cpu_limit
        self.ram_limit = ram_limit
        try:
            import psutil  # type: ignore
            self._psutil = psutil
        except Exception:
            self._psutil = None

    def cpu_percent(self) -> Optional[float]:
        if self._psutil:
            return float(self._psutil.cpu_percent(interval=0.1))
        try:
            load = os.getloadavg()[0]
            cores = os.cpu_count() or 1
            return round(min(100.0, load / cores * 100.0), 1)
        except Exception:
            return None

    def memory(self) -> Dict[str, Optional[float]]:
        if self._psutil:
            m = self._psutil.virtual_memory()
            return {"total_mb": round(m.total / 1048576, 1), "used_mb": round(m.used / 1048576, 1),
                    "percent": float(m.percent)}
        try:
            info = {}
            with open("/proc/meminfo", "r", encoding="utf-8") as fh:
                for line in fh:
                    k, _, v = line.partition(":")
                    info[k.strip()] = float(v.strip().split()[0]) / 1024.0
            total = info.get("MemTotal", 0.0)
            avail = info.get("MemAvailable", 0.0)
            used = total - avail
            return {"total_mb": round(total, 1), "used_mb": round(used, 1),
                    "percent": round(used / total * 100.0, 1) if total else None}
        except Exception:
            return {"total_mb": None, "used_mb": None, "percent": None}

    def disk(self, path: str = "/") -> Dict[str, Optional[float]]:
        try:
            u = shutil.disk_usage(path)
            return {"total_gb": round(u.total / 1073741824, 2), "used_gb": round(u.used / 1073741824, 2),
                    "percent": round(u.used / u.total * 100.0, 1)}
        except Exception:
            return {"total_gb": None, "used_gb": None, "percent": None}

    def battery(self) -> Dict[str, Any]:
        if self._psutil and hasattr(self._psutil, "sensors_battery"):
            try:
                b = self._psutil.sensors_battery()
                if b:
                    return {"percent": b.percent, "plugged": b.power_plugged, "available": True}
            except Exception:
                pass
        for base in ("/sys/class/power_supply/BAT0", "/sys/class/power_supply/BAT1"):
            try:
                with open(os.path.join(base, "capacity"), "r", encoding="utf-8") as fh:
                    return {"percent": float(fh.read().strip()), "plugged": None, "available": True}
            except Exception:
                continue
        return {"percent": None, "plugged": None, "available": False,
                "note": "no battery sensor on this machine"}

    def snapshot(self) -> Dict[str, Any]:
        return {"cpu_percent": self.cpu_percent(), "memory": self.memory(),
                "disk": self.disk(), "battery": self.battery(),
                "cores": os.cpu_count(), "at": _utc(),
                "source": "psutil" if self._psutil else "stdlib-fallback"}

    def admit(self, requires: Dict[str, float]) -> Dict[str, Any]:
        """Decide whether a task may start now given live resource pressure."""
        cpu = self.cpu_percent()
        mem = self.memory()
        batt = self.battery()
        if cpu is not None and cpu > self.cpu_limit:
            return {"admitted": False, "reason": f"cpu at {cpu}% above limit {self.cpu_limit}%"}
        if mem.get("percent") is not None and mem["percent"] > self.ram_limit:
            return {"admitted": False, "reason": f"memory at {mem['percent']}% above limit"}
        need_mb = float(requires.get("ram_mb", 0))
        if need_mb and mem.get("total_mb") and mem.get("used_mb") is not None:
            free = mem["total_mb"] - mem["used_mb"]
            if need_mb > free:
                return {"admitted": False, "reason": f"needs {need_mb} MB, only {round(free,1)} MB free"}
        if requires.get("battery_min") and batt.get("percent") is not None:
            if batt["percent"] < float(requires["battery_min"]):
                return {"admitted": False, "reason": f"battery {batt['percent']}% below required"}
        return {"admitted": True, "cpu_percent": cpu, "memory_percent": mem.get("percent")}

    def health(self) -> Dict[str, Any]:
        snap = self.snapshot()
        cpu = snap["cpu_percent"] or 0
        mem = snap["memory"].get("percent") or 0
        disk = snap["disk"].get("percent") or 0
        worst = max(cpu, mem, disk)
        snap["system_health"] = (
            "Excellent" if worst < 60 else "Good" if worst < 75 else
            "Degraded" if worst < 90 else "Critical"
        )
        return snap
