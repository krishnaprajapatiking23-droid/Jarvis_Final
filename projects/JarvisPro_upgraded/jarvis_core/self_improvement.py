"""Self-correction (Section 20) and self-improvement (Section 21).

This module does NOT duplicate `jarvis_core.learning.LearningEngine`; it uses
it as the experience store and adds the two missing roadmap capabilities:

S20 - Save Successful Correction
    A correction is only stored as reusable experience after it has been
    *verified*: problem / cause / correction / test / result. An unverified or
    failing correction is rejected, so Jarvis never learns a fix that did not
    actually work.

S21 - Generate Improvements + Improvement History + Regression Testing
    observe -> identify weakness -> propose improvement -> evaluate risk ->
    implement safely -> run regression tests -> accept / reject / rollback.
    Improvements are generated from real telemetry (analytics + experience
    records), never invented. Applying an improvement requires a regression
    suite to pass; if it fails, the change is rolled back from a real backup
    copy of the touched file, and the attempt is recorded either way.

State: SQLite `improvement.db` (tables `corrections`, `improvements`,
`improvement_runs`), plus file backups under `data/improvement_backups/`.
"""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Sequence

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DEF_DIR = os.path.join(_ROOT, "data")

# improvement lifecycle
PROPOSED = "proposed"
APPROVED = "approved"
APPLIED = "applied"
REJECTED = "rejected"
ROLLED_BACK = "rolled_back"
BLOCKED = "blocked"

RISK_LOW = "low"
RISK_MEDIUM = "medium"
RISK_HIGH = "high"

# Weakness detectors: (kind, threshold) - all fed by real telemetry.
FAILURE_RATE_THRESHOLD = 0.4
MIN_SAMPLES = 3
SLOW_SECONDS = 5.0
REPEAT_ERROR_THRESHOLD = 3


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class Improvement:
    id: str
    weakness: str
    target: str
    proposal: str
    rationale: str
    risk: str
    evidence: Dict[str, Any]
    status: str = PROPOSED
    created_at: str = field(default_factory=_utc)
    updated_at: str = field(default_factory=_utc)

    def to_dict(self) -> Dict[str, Any]:
        return {"id": self.id, "weakness": self.weakness, "target": self.target,
                "proposal": self.proposal, "rationale": self.rationale,
                "risk": self.risk, "evidence": self.evidence, "status": self.status,
                "created_at": self.created_at, "updated_at": self.updated_at}


class SelfImprovementEngine:
    capability = "self_improvement"

    def __init__(self, db_path: Optional[str] = None, kernel: Any = None,
                 learning: Any = None, analytics: Any = None,
                 backup_dir: Optional[str] = None,
                 project_root: Optional[str] = None):
        self.kernel = kernel
        self.learning = learning if learning is not None else getattr(kernel, "learning", None)
        self.analytics = analytics if analytics is not None else getattr(kernel, "analytics", None)
        self.project_root = os.path.abspath(project_root or _ROOT)
        path = db_path or os.path.join(_DEF_DIR, "improvement.db")
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self.backup_dir = backup_dir or os.path.join(os.path.dirname(path),
                                                     "improvement_backups")
        os.makedirs(self.backup_dir, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS corrections(
                    id TEXT PRIMARY KEY, problem TEXT, cause TEXT, correction TEXT,
                    test TEXT, result TEXT, verified INTEGER, confidence REAL,
                    reuses INTEGER DEFAULT 0, experience_id TEXT, trace_id TEXT,
                    created_at TEXT);
                CREATE TABLE IF NOT EXISTS improvements(
                    id TEXT PRIMARY KEY, weakness TEXT, target TEXT, proposal TEXT,
                    rationale TEXT, risk TEXT, evidence TEXT, status TEXT,
                    created_at TEXT, updated_at TEXT);
                CREATE TABLE IF NOT EXISTS improvement_runs(
                    id TEXT PRIMARY KEY, improvement_id TEXT, phase TEXT, ok INTEGER,
                    detail TEXT, created_at TEXT);
                CREATE INDEX IF NOT EXISTS idx_corr_problem ON corrections(problem);
                CREATE INDEX IF NOT EXISTS idx_runs_imp ON improvement_runs(improvement_id);
                """
            )
            self._conn.commit()

    # =============== S20: verified corrections ===============
    def save_correction(self, problem: str, cause: str, correction: str, *,
                        test: str = "", result: str = "", verified: bool = False,
                        confidence: float = 0.7,
                        trace_id: Optional[str] = None) -> Dict[str, Any]:
        """Store a correction as reusable experience - only if it is verified."""
        for name, value in (("problem", problem), ("cause", cause),
                            ("correction", correction)):
            if not isinstance(value, str) or not value.strip():
                return {"status": "invalid_input",
                        "error": f"{name} must be a non-empty string"}
        if not verified:
            return {"status": "rejected",
                    "error": "only verified successful corrections are saved "
                             "(no test evidence supplied)",
                    "problem": problem}
        if not str(test).strip():
            return {"status": "rejected",
                    "error": "a correction must name the test that proved it works"}
        cid = "CX-" + uuid.uuid4().hex[:10]
        experience_id = None
        if self.learning is not None:
            try:
                record = self.learning.learn_correction(problem, cause, correction,
                                                        trace_id=trace_id or "")
                experience_id = record.get("id")
                if experience_id and hasattr(self.learning, "save_correction"):
                    self.learning.save_correction(experience_id, worked=True)
            except Exception as exc:  # never lose the correction over telemetry
                experience_id = None
                self._log_run(cid, "experience", False, f"{type(exc).__name__}: {exc}")
        with self._lock:
            self._conn.execute(
                "INSERT INTO corrections(id, problem, cause, correction, test, result,"
                " verified, confidence, reuses, experience_id, trace_id, created_at)"
                " VALUES(?,?,?,?,?,?,?,?,0,?,?,?)",
                (cid, problem.strip(), cause.strip(), correction.strip(), test,
                 result, 1, float(confidence), experience_id, trace_id, _utc()))
            self._conn.commit()
        return {"status": "ok", "id": cid, "experience_id": experience_id,
                "verified": True, "problem": problem.strip(),
                "correction": correction.strip()}

    def find_correction(self, problem: str) -> Optional[Dict[str, Any]]:
        """Reuse a previously verified correction for a similar problem."""
        tokens = {w for w in str(problem or "").lower().split() if len(w) > 2}
        if not tokens:
            return None
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM corrections WHERE verified=1").fetchall()
        best, best_score = None, 0.0
        for row in rows:
            other = {w for w in row["problem"].lower().split() if len(w) > 2}
            if not other:
                continue
            score = len(tokens & other) / len(tokens | other)
            if score > best_score:
                best, best_score = row, score
        if best is None or best_score < 0.34:
            return None
        with self._lock:
            self._conn.execute("UPDATE corrections SET reuses = reuses + 1 WHERE id=?",
                               (best["id"],))
            self._conn.commit()
        item = dict(best)
        item["match"] = round(best_score, 3)
        item["verified"] = bool(item["verified"])
        return item

    def corrections(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM corrections ORDER BY created_at DESC, id DESC LIMIT ?",
                (int(limit),)).fetchall()
        return [dict(r) | {"verified": bool(r["verified"])} for r in rows]

    # =============== S21: improvement generation ===============
    def observe(self) -> Dict[str, Any]:
        """Collect the real telemetry that improvement proposals are based on."""
        observation: Dict[str, Any] = {"at": _utc(), "managers": [], "tools": [],
                                       "errors": [], "slow": [], "source": []}
        if self.analytics is not None:
            try:
                dash = self.analytics.dashboard()
                observation["source"].append("analytics")
                observation["overall"] = dash.get("overall", {})
                # Analytics scores are {name, uses, success_score, avg_ms}.
                observation["managers"] = list(dash.get("managers") or [])
                observation["tools"] = list(dash.get("tools") or [])
                observation["slow"] = [e for e in observation["managers"] + observation["tools"]
                                       if float(e.get("avg_ms") or 0) >= SLOW_SECONDS * 1000.0]
            except Exception as exc:
                observation["analytics_error"] = f"{type(exc).__name__}: {exc}"
        if self.learning is not None:
            try:
                observation["source"].append("experience")
                observation["experience"] = self.learning.stats()
                observation["outdated"] = len(self.learning.outdated())
                observation["errors"] = self._repeated_errors()
            except Exception as exc:
                observation["experience_error"] = f"{type(exc).__name__}: {exc}"
        return observation

    def _repeated_errors(self) -> List[Dict[str, Any]]:
        """Group recorded failure/error experiences by their error text."""
        if self.learning is None or not hasattr(self.learning, "db"):
            return []
        try:
            connection = self.learning.db.connect()
            rows = connection.execute(
                "SELECT COALESCE(NULLIF(error,''), failure) AS err, COUNT(*) AS n"
                " FROM experiences WHERE success=0 AND"
                " COALESCE(NULLIF(error,''), failure) <> '' GROUP BY err"
                " ORDER BY n DESC LIMIT 20").fetchall()
        except Exception:
            return []
        return [{"error": row["err"], "count": int(row["n"])} for row in rows]

    def identify_weaknesses(self, observation: Optional[Dict[str, Any]] = None
                            ) -> List[Dict[str, Any]]:
        """Turn telemetry into concrete weaknesses with evidence."""
        obs = observation or self.observe()
        weaknesses: List[Dict[str, Any]] = []
        for entry in list(obs.get("managers", [])) + list(obs.get("tools", [])):
            name = entry.get("name")
            total = int(entry.get("uses") or entry.get("total") or 0)
            rate = entry.get("success_score", entry.get("success_rate"))
            if name is None or rate is None or total < MIN_SAMPLES:
                continue
            if float(rate) <= 1.0 - FAILURE_RATE_THRESHOLD:
                weaknesses.append({
                    "kind": "low_success_rate", "target": str(name),
                    "evidence": {"success_rate": float(rate), "samples": total},
                    "detail": f"{name} succeeds only {float(rate):.0%} of {total} runs",
                })
        counts: Dict[str, int] = {}
        for err in obs.get("errors", []):
            key = str(err.get("error") or err.get("message") or "").strip()[:120]
            if key:
                counts[key] = counts.get(key, 0) + int(err.get("count", 1) or 1)
        for message, count in counts.items():
            if count >= REPEAT_ERROR_THRESHOLD:
                weaknesses.append({
                    "kind": "repeated_error", "target": message,
                    "evidence": {"occurrences": count},
                    "detail": f"error repeated {count} times: {message}",
                })
        for slow in obs.get("slow", []):
            seconds = float(slow.get("avg_ms") or 0) / 1000.0
            if seconds >= SLOW_SECONDS:
                weaknesses.append({
                    "kind": "slow_operation",
                    "target": str(slow.get("name") or "operation"),
                    "evidence": {"avg_seconds": round(seconds, 3)},
                    "detail": f"averages {seconds:.1f}s (>= {SLOW_SECONDS}s)",
                })
        if int(obs.get("outdated") or 0) > 0:
            weaknesses.append({
                "kind": "outdated_knowledge", "target": "experience store",
                "evidence": {"outdated": int(obs["outdated"])},
                "detail": f"{obs['outdated']} experience record(s) are stale",
            })
        return weaknesses

    def assess_risk(self, weakness: Dict[str, Any], target: str = "") -> str:
        """Risk of *applying* a change for this weakness."""
        kind = weakness.get("kind")
        path = target or str(weakness.get("target", ""))
        if kind in ("outdated_knowledge",):
            return RISK_LOW
        if path.endswith(".py") and ("kernel" in path or "brains" in path
                                     or "policy" in path or "security" in path):
            return RISK_HIGH
        if kind == "low_success_rate":
            return RISK_MEDIUM
        return RISK_MEDIUM if path.endswith(".py") else RISK_LOW

    def generate_improvements(self, observation: Optional[Dict[str, Any]] = None
                              ) -> List[Dict[str, Any]]:
        """Propose improvements for every detected weakness. No weakness, no
        proposal - Jarvis does not invent work for itself."""
        proposals = []
        for weakness in self.identify_weaknesses(observation):
            kind = weakness["kind"]
            target = weakness["target"]
            if kind == "low_success_rate":
                proposal = (f"add a fallback path and input validation for {target}, "
                            "then re-measure its success rate")
            elif kind == "repeated_error":
                proposal = ("add a specific handler and recovery path for this "
                            "recurring error instead of retrying blindly")
            elif kind == "slow_operation":
                proposal = (f"profile {target}, cache its repeated work and move it "
                            "off the request path")
            elif kind == "outdated_knowledge":
                proposal = "retire stale experience records so planning stops using them"
            else:
                proposal = f"investigate {target}"
            risk = self.assess_risk(weakness)
            imp = Improvement(id="IMP-" + uuid.uuid4().hex[:8], weakness=kind,
                              target=target, proposal=proposal,
                              rationale=weakness["detail"], risk=risk,
                              evidence=weakness["evidence"])
            self._store_improvement(imp)
            proposals.append(imp.to_dict())
        return proposals

    def _store_improvement(self, imp: Improvement) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO improvements(id, weakness, target, proposal,"
                " rationale, risk, evidence, status, created_at, updated_at)"
                " VALUES(?,?,?,?,?,?,?,?,?,?)",
                (imp.id, imp.weakness, imp.target, imp.proposal, imp.rationale,
                 imp.risk, json.dumps(imp.evidence, default=str), imp.status,
                 imp.created_at, imp.updated_at))
            self._conn.commit()

    def _log_run(self, improvement_id: str, phase: str, ok: bool, detail: str) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO improvement_runs(id, improvement_id, phase, ok, detail,"
                " created_at) VALUES(?,?,?,?,?,?)",
                ("IR-" + uuid.uuid4().hex[:10], improvement_id, phase,
                 1 if ok else 0, detail[:4000], _utc()))
            self._conn.commit()

    def _set_status(self, improvement_id: str, status: str) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE improvements SET status=?, updated_at=? WHERE id=?",
                (status, _utc(), improvement_id))
            self._conn.commit()

    def get_improvement(self, improvement_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            row = self._conn.execute("SELECT * FROM improvements WHERE id=?",
                                     (improvement_id,)).fetchone()
        if row is None:
            return None
        item = dict(row)
        try:
            item["evidence"] = json.loads(item["evidence"])
        except (TypeError, json.JSONDecodeError):
            pass
        return item

    def history(self, status: Optional[str] = None,
                limit: int = 50) -> List[Dict[str, Any]]:
        sql = "SELECT * FROM improvements"
        params: List[Any] = []
        if status:
            sql += " WHERE status=?"
            params.append(status)
        sql += " ORDER BY created_at DESC, id DESC LIMIT ?"
        params.append(int(limit))
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
            out = []
            for row in rows:
                item = dict(row)
                try:
                    item["evidence"] = json.loads(item["evidence"])
                except (TypeError, json.JSONDecodeError):
                    pass
                item["runs"] = [dict(r) | {"ok": bool(r["ok"])} for r in self._conn.execute(
                    "SELECT phase, ok, detail, created_at FROM improvement_runs"
                    " WHERE improvement_id=? ORDER BY created_at", (item["id"],)).fetchall()]
                out.append(item)
        return out

    # =============== regression testing ===============
    def run_regression(self, suites: Sequence[str] = (), *,
                       improvement_id: str = "-",
                       timeout: float = 600.0) -> Dict[str, Any]:
        """Run real test scripts in a subprocess. Absent suite -> unavailable,
        never a fake pass."""
        if not suites:
            return {"ok": False, "status": "invalid_input",
                    "error": "no regression suites supplied - nothing was verified"}
        results = []
        for suite in suites:
            path = suite if os.path.isabs(suite) else os.path.join(self.project_root, suite)
            if not os.path.isfile(path):
                results.append({"suite": suite, "ok": False, "status": "unavailable",
                                "detail": f"{suite} not found"})
                continue
            start = time.monotonic()
            try:
                proc = subprocess.run([sys.executable, path], cwd=self.project_root,
                                      capture_output=True, text=True, timeout=timeout)
                tail = (proc.stdout or "").strip().splitlines()[-3:]
                results.append({"suite": suite, "ok": proc.returncode == 0,
                                "status": "ok" if proc.returncode == 0 else "failure",
                                "returncode": proc.returncode,
                                "duration": round(time.monotonic() - start, 3),
                                "detail": " | ".join(tail) or (proc.stderr or "")[-400:]})
            except subprocess.TimeoutExpired:
                results.append({"suite": suite, "ok": False, "status": "timeout",
                                "detail": f"suite exceeded {timeout}s"})
            except Exception as exc:
                results.append({"suite": suite, "ok": False, "status": "failure",
                                "detail": f"{type(exc).__name__}: {exc}"})
        ok = all(r["ok"] for r in results)
        summary = {"ok": ok, "status": "ok" if ok else "failure",
                   "suites": results,
                   "passed": sum(1 for r in results if r["ok"]),
                   "failed": sum(1 for r in results if not r["ok"])}
        self._log_run(improvement_id, "regression", ok, json.dumps(summary)[:3800])
        return summary

    # =============== safe application ===============
    @staticmethod
    def _invalidate_bytecode(path: str) -> None:
        """Drop cached bytecode for a modified module.

        CPython validates a .pyc using the source size and mtime *in whole
        seconds*. A same-length edit inside the same second therefore keeps the
        stale .pyc valid, and a regression suite would test the OLD code and
        report a false pass. Removing the cache entry (and touching the source)
        makes the regression run test what was actually written.
        """
        if not path.endswith(".py"):
            return
        directory, name = os.path.split(path)
        cache = os.path.join(directory, "__pycache__")
        stem = name[:-3]
        try:
            if os.path.isdir(cache):
                for entry in os.listdir(cache):
                    if entry.startswith(stem + ".") and entry.endswith(".pyc"):
                        os.remove(os.path.join(cache, entry))
            legacy = path + "c"
            if os.path.isfile(legacy):
                os.remove(legacy)
            os.utime(path, None)
        except OSError:
            pass

    def _backup(self, path: str, improvement_id: str) -> str:
        dest = os.path.join(self.backup_dir,
                            f"{improvement_id}_{os.path.basename(path)}.bak")
        shutil.copy2(path, dest)
        return dest

    def apply_improvement(self, improvement_id: str, *, target_file: str,
                          change: Callable[[str], Any],
                          regression_suites: Sequence[str] = (),
                          approve_high_risk: bool = False) -> Dict[str, Any]:
        """Implement safely: backup -> change -> regression -> accept/rollback.

        `change(path)` performs the edit. High-risk targets require explicit
        approval, so self-improvement can never silently rewrite the kernel or
        the policy engine.
        """
        imp = self.get_improvement(improvement_id)
        if imp is None:
            return {"status": "invalid_input", "error": f"unknown improvement {improvement_id}"}
        path = target_file if os.path.isabs(target_file) else os.path.join(
            self.project_root, target_file)
        real = os.path.realpath(path)
        if not real.startswith(self.project_root + os.sep):
            self._log_run(improvement_id, "guard", False, "path outside project root")
            self._set_status(improvement_id, BLOCKED)
            return {"status": "permission_denied",
                    "error": f"refusing to modify {target_file} outside the project root"}
        if not os.path.isfile(real):
            return {"status": "not_found", "error": f"{target_file} does not exist"}
        risk = self.assess_risk({"kind": imp["weakness"], "target": target_file},
                                target_file)
        if risk == RISK_HIGH and not approve_high_risk:
            self._log_run(improvement_id, "risk", False,
                          f"high-risk target {target_file} needs approval")
            self._set_status(improvement_id, BLOCKED)
            return {"status": "permission_denied", "risk": risk,
                    "error": f"{target_file} is high risk; explicit approval required"}
        if not regression_suites:
            self._log_run(improvement_id, "guard", False, "no regression suites")
            self._set_status(improvement_id, BLOCKED)
            return {"status": "invalid_input", "risk": risk,
                    "error": "an improvement may not be applied without regression tests"}
        backup = self._backup(real, improvement_id)
        self._log_run(improvement_id, "backup", True, backup)
        try:
            change(real)
        except Exception as exc:
            shutil.copy2(backup, real)
            self._invalidate_bytecode(real)
            self._log_run(improvement_id, "apply", False, f"{type(exc).__name__}: {exc}")
            self._set_status(improvement_id, REJECTED)
            return {"status": "failure", "rolled_back": True,
                    "error": f"change raised {type(exc).__name__}: {exc}"}
        self._invalidate_bytecode(real)
        self._log_run(improvement_id, "apply", True, f"modified {target_file}")
        regression = self.run_regression(regression_suites,
                                         improvement_id=improvement_id)
        if not regression["ok"]:
            shutil.copy2(backup, real)
            self._invalidate_bytecode(real)
            self._log_run(improvement_id, "rollback", True,
                          "regression failed - file restored from backup")
            self._set_status(improvement_id, ROLLED_BACK)
            return {"status": "rolled_back", "accepted": False, "risk": risk,
                    "regression": regression, "backup": backup,
                    "error": "regression tests failed; change reverted"}
        self._set_status(improvement_id, APPLIED)
        if self.learning is not None:
            try:
                self.learning.learn_success(f"self-improvement {imp['weakness']}",
                                            imp["proposal"], "regression passed")
            except Exception:
                pass
        return {"status": "ok", "accepted": True, "risk": risk,
                "regression": regression, "backup": backup,
                "improvement": self.get_improvement(improvement_id)}

    def reject(self, improvement_id: str, reason: str) -> Dict[str, Any]:
        if self.get_improvement(improvement_id) is None:
            return {"status": "invalid_input", "error": f"unknown improvement {improvement_id}"}
        self._log_run(improvement_id, "reject", True, reason)
        self._set_status(improvement_id, REJECTED)
        return {"status": "ok", "id": improvement_id, "state": REJECTED, "reason": reason}

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            imp_rows = self._conn.execute(
                "SELECT status, COUNT(*) n FROM improvements GROUP BY status").fetchall()
            corrections = self._conn.execute(
                "SELECT COUNT(*) n, COALESCE(SUM(reuses),0) r FROM corrections").fetchone()
        return {"improvements": {r["status"]: r["n"] for r in imp_rows},
                "corrections": corrections["n"], "correction_reuses": corrections["r"]}

    def health(self) -> Dict[str, Any]:
        return {"available": True, "learning": self.learning is not None,
                "analytics": self.analytics is not None, **self.stats()}

    def run(self, action: str, **kwargs: Any) -> Any:
        actions = {
            "observe": self.observe,
            "weaknesses": lambda: self.identify_weaknesses(kwargs.get("observation")),
            "generate": lambda: self.generate_improvements(kwargs.get("observation")),
            "apply": lambda: self.apply_improvement(
                kwargs["improvement_id"], target_file=kwargs["target_file"],
                change=kwargs["change"],
                regression_suites=kwargs.get("regression_suites", ()),
                approve_high_risk=bool(kwargs.get("approve_high_risk"))),
            "reject": lambda: self.reject(kwargs["improvement_id"],
                                          kwargs.get("reason", "rejected")),
            "save_correction": lambda: self.save_correction(
                kwargs["problem"], kwargs["cause"], kwargs["correction"],
                test=kwargs.get("test", ""), result=kwargs.get("result", ""),
                verified=bool(kwargs.get("verified"))),
            "find_correction": lambda: self.find_correction(kwargs["problem"]),
            "regression": lambda: self.run_regression(kwargs.get("suites", ())),
            "history": lambda: self.history(kwargs.get("status"), kwargs.get("limit", 50)),
            "health": self.health,
        }
        if action not in actions:
            return {"status": "invalid_input",
                    "error": f"unknown self-improvement action {action!r}",
                    "available": sorted(actions)}
        return actions[action]()


__all__ = ["SelfImprovementEngine", "Improvement", "PROPOSED", "APPLIED",
           "REJECTED", "ROLLED_BACK", "BLOCKED", "RISK_LOW", "RISK_MEDIUM",
           "RISK_HIGH"]
