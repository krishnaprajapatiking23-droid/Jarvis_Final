"""
==========================================
JARVIS PRO - Corruption detection & automatic recovery
==========================================

Roadmap sections 26 (automatic recovery) and 27 (corruption detection).

What this does, for real
    * checks every SQLite database Jarvis owns with PRAGMA integrity_check
    * checks every JSON config/state file by actually parsing it
    * spots empty files, truncated databases and leftover journals
    * keeps rotating backups of healthy files and restores from them
    * quarantines unrecoverable files instead of deleting user data
    * records every incident so recovery can be audited later

It never reports "recovered" without re-verifying the resource afterwards, and
it never silently swallows an error: outcomes are ok / degraded / failed /
unavailable / invalid_input / not_found.
"""

from __future__ import annotations

import glob
import json
import os
import shutil
import sqlite3
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Iterable, Optional

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DEF_DIR = os.path.join(_ROOT, "data")

# problem kinds
MISSING = "missing"
EMPTY = "empty_file"
CORRUPT = "corrupt"
UNREADABLE = "unreadable"
BAD_JSON = "invalid_json"
STALE_JOURNAL = "stale_journal"

# outcomes
OK = "ok"
REPAIRED = "repaired"
RESTORED = "restored"
REBUILT = "rebuilt"
QUARANTINED = "quarantined"
FAILED = "failed"

MAX_BACKUPS = 3
SAFE_SUFFIXES = (".db", ".json")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


class RecoveryManager:
    """Finds damaged Jarvis state and puts it back together safely."""

    capability = "recovery"

    def __init__(self, db_path: Optional[str] = None, kernel: Any = None,
                 data_dir: Optional[str] = None,
                 backup_dir: Optional[str] = None) -> None:
        self.kernel = kernel
        self.data_dir = os.path.abspath(data_dir or _DEF_DIR)
        os.makedirs(self.data_dir, exist_ok=True)
        self.db_path = db_path or os.path.join(self.data_dir, "recovery.db")
        parent = os.path.dirname(os.path.abspath(self.db_path))
        if parent:
            os.makedirs(parent, exist_ok=True)
        self.backup_dir = os.path.abspath(backup_dir or os.path.join(self.data_dir, "backups"))
        self.quarantine_dir = os.path.join(self.data_dir, "quarantine")
        os.makedirs(self.backup_dir, exist_ok=True)
        os.makedirs(self.quarantine_dir, exist_ok=True)
        self._lock = threading.RLock()
        self._init_db()

    # ------------------------------------------------ incident log

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_db(self) -> None:
        with self._lock, self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS incidents (
                    id TEXT PRIMARY KEY,
                    resource TEXT,
                    problem TEXT,
                    detail TEXT,
                    action TEXT,
                    outcome TEXT,
                    verified INTEGER,
                    at TEXT
                );
                CREATE TABLE IF NOT EXISTS backups (
                    id TEXT PRIMARY KEY,
                    resource TEXT,
                    path TEXT,
                    bytes INTEGER,
                    at TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_inc_res ON incidents(resource);
                CREATE INDEX IF NOT EXISTS idx_bk_res ON backups(resource);
                """
            )

    def _log(self, resource: str, problem: str, detail: str, action: str,
             outcome: str, verified: bool) -> str:
        incident = _id("RC")
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO incidents VALUES (?,?,?,?,?,?,?,?)",
                (incident, resource, problem, str(detail)[:3800], action, outcome,
                 1 if verified else 0, _now()),
            )
        if self.kernel is not None and getattr(self.kernel, "analytics", None):
            try:
                self.kernel.analytics.record("recovery", action, success=outcome in
                                             (OK, REPAIRED, RESTORED, REBUILT))
            except Exception:
                pass  # analytics must never break recovery
        return incident

    def incidents(self, limit: int = 50, resource: str = "") -> list[dict[str, Any]]:
        sql = "SELECT * FROM incidents"
        params: list[Any] = []
        if resource:
            sql += " WHERE resource = ?"
            params.append(resource)
        sql += " ORDER BY at DESC, rowid DESC LIMIT ?"
        params.append(int(limit))
        with self._lock, self._connect() as conn:
            return [dict(r) for r in conn.execute(sql, params)]

    # ------------------------------------------------ S27 detection

    def check_sqlite(self, path: str) -> dict[str, Any]:
        """Real integrity check of one SQLite database."""
        if not isinstance(path, str) or not path.strip():
            return {"status": "invalid_input", "error": "a database path is required"}
        if not os.path.exists(path):
            return {"status": "not_found", "problem": MISSING,
                    "error": f"{os.path.basename(path)} does not exist"}
        size = os.path.getsize(path)
        if size == 0:
            return {"status": "corrupt", "problem": EMPTY, "bytes": 0,
                    "error": f"{os.path.basename(path)} is a zero-byte file"}
        try:
            with open(path, "rb") as fh:
                header = fh.read(16)
        except OSError as exc:
            return {"status": "corrupt", "problem": UNREADABLE, "error": str(exc)}
        if not header.startswith(b"SQLite format 3"):
            return {"status": "corrupt", "problem": CORRUPT, "bytes": size,
                    "error": f"{os.path.basename(path)} is not a SQLite database "
                             f"(bad header {header[:16]!r})"}
        # A leftover journal must be noticed BEFORE connecting: opening the
        # database makes SQLite roll the hot journal back and delete it, which
        # would hide the fact that Jarvis exited mid-write.
        journal = path + "-journal"
        stale = os.path.exists(journal) and os.path.getsize(journal) > 0
        try:
            conn = sqlite3.connect(path, timeout=5)
            try:
                result = conn.execute("PRAGMA integrity_check").fetchone()[0]
                tables = conn.execute(
                    "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table'"
                ).fetchone()[0]
            finally:
                conn.close()
        except sqlite3.DatabaseError as exc:
            return {"status": "corrupt", "problem": CORRUPT, "bytes": size,
                    "error": f"{type(exc).__name__}: {exc}"}
        except Exception as exc:
            return {"status": "unavailable", "problem": UNREADABLE,
                    "error": f"{type(exc).__name__}: {exc}"}
        if str(result).lower() != "ok":
            return {"status": "corrupt", "problem": CORRUPT, "bytes": size,
                    "error": f"integrity_check reported: {result}"}
        return {"status": OK, "bytes": size, "tables": tables,
                "stale_journal": stale, "integrity": "ok"}

    def check_json(self, path: str) -> dict[str, Any]:
        """Real parse of one JSON state/config file."""
        if not isinstance(path, str) or not path.strip():
            return {"status": "invalid_input", "error": "a file path is required"}
        if not os.path.exists(path):
            return {"status": "not_found", "problem": MISSING,
                    "error": f"{os.path.basename(path)} does not exist"}
        if os.path.getsize(path) == 0:
            return {"status": "corrupt", "problem": EMPTY,
                    "error": f"{os.path.basename(path)} is empty"}
        try:
            with open(path, "r", encoding="utf-8") as fh:
                json.load(fh)
        except json.JSONDecodeError as exc:
            return {"status": "corrupt", "problem": BAD_JSON,
                    "error": f"line {exc.lineno} column {exc.colno}: {exc.msg}"}
        except (OSError, UnicodeDecodeError) as exc:
            return {"status": "corrupt", "problem": UNREADABLE,
                    "error": f"{type(exc).__name__}: {exc}"}
        return {"status": OK, "bytes": os.path.getsize(path)}

    def resources(self) -> list[str]:
        """Every state file recovery is responsible for."""
        found: list[str] = []
        for suffix in SAFE_SUFFIXES:
            found.extend(sorted(glob.glob(os.path.join(self.data_dir, f"*{suffix}"))))
        return [p for p in found
                if os.path.abspath(p) != os.path.abspath(self.db_path)]

    def scan(self, paths: Optional[Iterable[str]] = None) -> dict[str, Any]:
        """Check every resource and report exactly what is wrong."""
        targets = list(paths) if paths is not None else self.resources()
        healthy: list[str] = []
        damaged: list[dict[str, Any]] = []
        for path in targets:
            if path.endswith(".json"):
                result = self.check_json(path)
            elif path.endswith(".db"):
                result = self.check_sqlite(path)
            else:
                damaged.append({"resource": path, "problem": "unsupported",
                                "error": "only .db and .json state files are checked"})
                continue
            name = os.path.basename(path)
            if result["status"] == OK:
                healthy.append(name)
                if result.get("stale_journal"):
                    damaged.append({"resource": path, "name": name,
                                    "problem": STALE_JOURNAL,
                                    "error": "a non-empty -journal file was left behind"})
            else:
                damaged.append({"resource": path, "name": name,
                                "problem": result.get("problem", CORRUPT),
                                "error": result.get("error", "unknown problem"),
                                "status": result["status"]})
        return {"status": OK if not damaged else "degraded",
                "checked": len(targets), "healthy": healthy,
                "damaged": damaged, "damaged_count": len(damaged),
                "scanned_at": _now()}

    # ------------------------------------------------ backups

    def backup(self, path: str) -> dict[str, Any]:
        """Copy a *verified healthy* resource into the rotating backup set."""
        if not os.path.exists(path):
            return {"status": "not_found", "error": f"{path} does not exist"}
        check = self.check_sqlite(path) if path.endswith(".db") else self.check_json(path)
        if check["status"] != OK:
            return {"status": "failed", "error": "refusing to back up a damaged file: "
                                                 f"{check.get('error')}"}
        stamp = time.strftime("%Y%m%d-%H%M%S") + f"-{uuid.uuid4().hex[:4]}"
        name = os.path.basename(path)
        dest = os.path.join(self.backup_dir, f"{name}.{stamp}.bak")
        shutil.copy2(path, dest)
        size = os.path.getsize(dest)
        with self._lock, self._connect() as conn:
            conn.execute("INSERT INTO backups VALUES (?,?,?,?,?)",
                         (_id("BK"), name, dest, size, _now()))
        pruned = self._prune(name)
        return {"status": OK, "backup": dest, "bytes": size, "pruned": pruned}

    def backup_all(self) -> dict[str, Any]:
        done, skipped = [], []
        for path in self.resources():
            result = self.backup(path)
            (done if result["status"] == OK else skipped).append(
                {"resource": os.path.basename(path), "detail": result.get("error", "ok")})
        return {"status": OK if done else "degraded", "backed_up": len(done),
                "skipped": skipped}

    def _prune(self, name: str) -> int:
        # Sort by modification time, not filename: backup names carry a random
        # suffix, so lexical order could prune the newest copy.
        keep = sorted(glob.glob(os.path.join(self.backup_dir, f"{name}.*.bak")),
                      key=lambda p: (os.path.getmtime(p), p))
        drop = keep[:-MAX_BACKUPS] if len(keep) > MAX_BACKUPS else []
        for path in drop:
            try:
                os.remove(path)
                with self._lock, self._connect() as conn:
                    conn.execute("DELETE FROM backups WHERE path = ?", (path,))
            except OSError:
                pass
        return len(drop)

    def latest_backup(self, name: str) -> Optional[str]:
        found = sorted(glob.glob(os.path.join(self.backup_dir, f"{name}.*.bak")),
                       key=lambda p: (os.path.getmtime(p), p))
        return found[-1] if found else None

    # ------------------------------------------------ S26 recovery

    def _quarantine(self, path: str) -> str:
        dest = os.path.join(self.quarantine_dir,
                            f"{os.path.basename(path)}.{time.strftime('%Y%m%d-%H%M%S')}"
                            f".{uuid.uuid4().hex[:4]}.corrupt")
        shutil.move(path, dest)
        return dest

    def _verify(self, path: str) -> dict[str, Any]:
        return self.check_sqlite(path) if path.endswith(".db") else self.check_json(path)

    def repair(self, path: str, *, problem: str = "", rebuild: bool = True) -> dict[str, Any]:
        """Repair one resource. Order: journal cleanup -> backup -> rebuild.

        Every branch re-verifies the file afterwards; a repair that does not
        verify is reported as failed, never as success.
        """
        if not isinstance(path, str) or not path.strip():
            return {"status": "invalid_input", "error": "a resource path is required"}
        name = os.path.basename(path)
        problem = problem or self._verify(path).get("problem", CORRUPT)

        # 1. stale journal: safe to clear, the database itself verified ok
        if problem == STALE_JOURNAL:
            journal = path + "-journal"
            try:
                if os.path.exists(journal):
                    os.remove(journal)
            except OSError as exc:
                self._log(name, problem, str(exc), "clear_journal", FAILED, False)
                return {"status": FAILED, "error": f"could not remove {journal}: {exc}"}
            after = self._verify(path)
            ok = after["status"] == OK and not after.get("stale_journal")
            self._log(name, problem, "journal removed", "clear_journal",
                      REPAIRED if ok else FAILED, ok)
            return {"status": REPAIRED if ok else FAILED, "action": "clear_journal",
                    "verified": ok, "resource": name}

        # 2. restore from the newest healthy backup
        backup = self.latest_backup(name)
        quarantined = None
        if backup:
            if os.path.exists(path):
                quarantined = self._quarantine(path)
            shutil.copy2(backup, path)
            after = self._verify(path)
            if after["status"] == OK:
                self._log(name, problem, f"restored from {os.path.basename(backup)}",
                          "restore_backup", RESTORED, True)
                return {"status": RESTORED, "action": "restore_backup",
                        "backup": backup, "quarantined": quarantined,
                        "verified": True, "resource": name}
            self._log(name, problem, f"backup also failed: {after.get('error')}",
                      "restore_backup", FAILED, False)

        # 3. rebuild empty state so Jarvis can keep running
        if not rebuild:
            self._log(name, problem, "rebuild not permitted", "none", FAILED, False)
            return {"status": FAILED, "resource": name,
                    "error": f"{name} is {problem} and no healthy backup exists"}
        if os.path.exists(path) and quarantined is None:
            quarantined = self._quarantine(path)
        try:
            if path.endswith(".db"):
                conn = sqlite3.connect(path, timeout=5)
                conn.execute("PRAGMA journal_mode=WAL")
                conn.close()
            else:
                with open(path, "w", encoding="utf-8") as fh:
                    json.dump({}, fh)
        except Exception as exc:
            self._log(name, problem, f"{type(exc).__name__}: {exc}", "rebuild", FAILED, False)
            return {"status": FAILED, "resource": name,
                    "error": f"rebuild failed: {type(exc).__name__}: {exc}"}
        after = self._verify(path)
        ok = after["status"] == OK
        self._log(name, problem, "rebuilt empty state; damaged copy quarantined",
                  "rebuild", REBUILT if ok else FAILED, ok)
        return {"status": REBUILT if ok else FAILED, "action": "rebuild",
                "quarantined": quarantined, "verified": ok, "resource": name,
                "data_loss": True}

    def recover(self, paths: Optional[Iterable[str]] = None, *,
                rebuild: bool = True) -> dict[str, Any]:
        """Scan, repair everything damaged, then re-scan to prove the result."""
        first = self.scan(paths)
        if not first["damaged"]:
            return {"status": OK, "repaired": [], "failed": [],
                    "message": "all state files verified healthy",
                    "checked": first["checked"]}
        repaired, failed = [], []
        for item in first["damaged"]:
            if item.get("problem") == "unsupported":
                failed.append({**item, "outcome": FAILED})
                continue
            outcome = self.repair(item["resource"], problem=item["problem"],
                                  rebuild=rebuild)
            record = {"resource": item.get("name", item["resource"]),
                      "problem": item["problem"], "outcome": outcome["status"],
                      "detail": outcome.get("error", outcome.get("action", ""))}
            (repaired if outcome["status"] in (REPAIRED, RESTORED, REBUILT)
             else failed).append(record)
        after = self.scan(paths)
        return {"status": OK if not after["damaged"] else "degraded",
                "repaired": repaired, "failed": failed,
                "still_damaged": after["damaged"],
                "checked": first["checked"]}

    # ------------------------------------------------ reporting

    def stats(self) -> dict[str, Any]:
        with self._lock, self._connect() as conn:
            total = conn.execute("SELECT COUNT(*) FROM incidents").fetchone()[0]
            verified = conn.execute("SELECT COUNT(*) FROM incidents WHERE verified = 1"
                                    ).fetchone()[0]
            by_outcome = {r["outcome"]: r["n"] for r in conn.execute(
                "SELECT outcome, COUNT(*) AS n FROM incidents GROUP BY outcome")}
            backups = conn.execute("SELECT COUNT(*) FROM backups").fetchone()[0]
        return {"incidents": total, "verified_repairs": verified,
                "by_outcome": by_outcome, "backups": backups,
                "quarantined": len(os.listdir(self.quarantine_dir))
                if os.path.isdir(self.quarantine_dir) else 0}

    def health(self) -> dict[str, Any]:
        try:
            scan = self.scan()
            return {"available": True, "data_dir": self.data_dir,
                    "resources": scan["checked"], "damaged": scan["damaged_count"],
                    "state": scan["status"], **self.stats()}
        except Exception as exc:
            return {"available": False, "error": f"{type(exc).__name__}: {exc}"}

    def run(self, action: str = "scan", **kwargs: Any) -> dict[str, Any]:
        actions = {
            "scan": self.scan,
            "check_sqlite": self.check_sqlite,
            "check_json": self.check_json,
            "backup": self.backup,
            "backup_all": self.backup_all,
            "repair": self.repair,
            "recover": self.recover,
            "incidents": lambda **kw: {"status": OK, "incidents": self.incidents(**kw)},
            "stats": lambda: {"status": OK, **self.stats()},
            "health": lambda: {"status": OK, **self.health()},
        }
        handler = actions.get(str(action))
        if handler is None:
            return {"status": "invalid_input",
                    "error": f"unknown recovery action '{action}'",
                    "supported": sorted(actions)}
        try:
            return handler(**kwargs)
        except TypeError as exc:
            return {"status": "invalid_input",
                    "error": f"bad arguments for '{action}': {exc}"}


_MANAGER: Optional[RecoveryManager] = None


def get_recovery_manager(db_path: Optional[str] = None, kernel: Any = None,
                         data_dir: Optional[str] = None) -> RecoveryManager:
    global _MANAGER
    if _MANAGER is None or db_path is not None:
        _MANAGER = RecoveryManager(db_path, kernel=kernel, data_dir=data_dir)
    return _MANAGER
