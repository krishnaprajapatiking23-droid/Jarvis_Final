"""S11 Policy & permission engine + S1 human approval checkpoints + S24 audit.

- capability permissions with scope / granted_at / expires_at / granted_by / reason
- temporary permissions that genuinely stop working after expiry
- risk classification and allow / deny / ask decisions
- protected operations that can never be auto-approved
- approval checkpoints with blocking wait + timeout
- append-only audit log with secret redaction
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

_DEF_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")

RISK_SAFE, RISK_LOW, RISK_MEDIUM, RISK_HIGH, RISK_CRITICAL = (
    "safe", "low", "medium", "high", "critical",
)
RISK_ORDER = {RISK_SAFE: 0, RISK_LOW: 1, RISK_MEDIUM: 2, RISK_HIGH: 3, RISK_CRITICAL: 4}

# Operations that must never execute without explicit human approval.
PROTECTED_PATTERNS: Tuple[Tuple[str, str], ...] = (
    (r"rm\s+-rf\s+/(?!\w)", RISK_CRITICAL),
    (r"\bformat\s+[a-z]:", RISK_CRITICAL),
    (r"\bmkfs\b", RISK_CRITICAL),
    (r"\bdd\s+if=.*of=/dev/", RISK_CRITICAL),
    (r"\bshutdown\b|\breboot\b|\brestart\s+pc\b", RISK_HIGH),
    (r"\bdel(ete)?\b.*\b(system32|windows)\b", RISK_CRITICAL),
    (r"\btaskkill\b|\bkill\s+-9\b", RISK_HIGH),
    (r"\bregistry\b|\bregedit\b", RISK_HIGH),
    (r"\bgit\s+push\s+--force\b", RISK_HIGH),
    (r"\bpip\s+install\b|\bnpm\s+install\b", RISK_MEDIUM),
    (r"\bsend\b.*\b(email|whatsapp|telegram|discord)\b", RISK_MEDIUM),
    (r"\btransfer\b|\bpayment\b|\bbank\b", RISK_CRITICAL),
)

SECRET_KEYS = ("password", "passwd", "token", "secret", "api_key", "apikey", "authorization", "cookie", "private_key")
_SECRET_RE = re.compile(
    r"(?i)\b(" + "|".join(SECRET_KEYS) + r")\b\s*[:=]\s*(\"[^\"]*\"|'[^']*'|[^\s,;]+)"
)


def _utc() -> datetime:
    return datetime.now(timezone.utc)


def redact(value: Any) -> Any:
    """Remove secrets before anything is written to a log."""
    if isinstance(value, dict):
        return {
            k: ("***REDACTED***" if any(s in str(k).lower() for s in SECRET_KEYS) else redact(v))
            for k, v in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [redact(v) for v in value]
    if isinstance(value, str):
        return _SECRET_RE.sub(lambda m: f"{m.group(1)}=***REDACTED***", value)
    return value


@dataclass
class Permission:
    scope: str
    granted_at: str
    granted_by: str
    reason: str
    expires_at: Optional[str] = None
    revoked: bool = False
    perm_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])

    def is_active(self, now: Optional[datetime] = None) -> bool:
        if self.revoked:
            return False
        if not self.expires_at:
            return True
        now = now or _utc()
        return now <= datetime.fromisoformat(self.expires_at)

    def covers(self, scope: str) -> bool:
        """`files.*` covers `files.delete`; `*` covers everything."""
        if self.scope == "*":
            return True
        if self.scope == scope:
            return True
        if self.scope.endswith(".*"):
            return scope.startswith(self.scope[:-1])
        return False

    def to_dict(self) -> Dict[str, Any]:
        d = dict(self.__dict__)
        d["active"] = self.is_active()
        return d


@dataclass
class Decision:
    effect: str  # allow | deny | ask
    scope: str
    risk: str
    reasons: List[str]
    permission_id: Optional[str] = None
    protected: bool = False

    @property
    def allowed(self) -> bool:
        return self.effect == "allow"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "effect": self.effect, "scope": self.scope, "risk": self.risk,
            "reasons": list(self.reasons), "permission_id": self.permission_id,
            "protected": self.protected,
        }


class ApprovalRequest:
    def __init__(self, request_id: str, scope: str, summary: str, risk: str, timeout: float,
                 details: Optional[Dict[str, Any]] = None):
        self.request_id = request_id
        self.scope = scope
        self.summary = summary
        self.risk = risk
        self.timeout = timeout
        self.details = details or {}
        self.created = time.time()
        self.state = "pending"
        self.approved_by: Optional[str] = None
        self.note: Optional[str] = None
        self._event = threading.Event()

    def resolve(self, approved: bool, by: str = "user", note: Optional[str] = None) -> None:
        self.state = "approved" if approved else "denied"
        self.approved_by = by
        self.note = note
        self._event.set()

    def wait(self) -> str:
        """Blocks until resolved or timed out. Timeout is treated as denial."""
        remaining = self.timeout - (time.time() - self.created)
        if remaining > 0:
            self._event.wait(remaining)
        if not self._event.is_set():
            self.state = "timeout"
        return self.state

    def to_dict(self) -> Dict[str, Any]:
        return {
            "request_id": self.request_id, "scope": self.scope, "summary": self.summary,
            "risk": self.risk, "state": self.state, "approved_by": self.approved_by,
            "note": self.note, "age_s": round(time.time() - self.created, 2),
        }


class PolicyEngine:
    def __init__(self, db_path: Optional[str] = None, default_ask_from: str = RISK_MEDIUM):
        os.makedirs(_DEF_DIR, exist_ok=True)
        self.db_path = db_path or os.path.join(_DEF_DIR, "policy.db")
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self.default_ask_from = default_ask_from
        self.pending: Dict[str, ApprovalRequest] = {}
        self._approval_hook = None
        self._init_db()

    def _init_db(self) -> None:
        with self._lock:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS permissions (
                    perm_id TEXT PRIMARY KEY, subject TEXT, scope TEXT, granted_at TEXT,
                    expires_at TEXT, granted_by TEXT, reason TEXT, revoked INTEGER DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS audit (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, trace_id TEXT, subject TEXT,
                    command TEXT, tool TEXT, scope TEXT, decision TEXT, risk TEXT,
                    permission_id TEXT, result TEXT, at TEXT, extra TEXT
                );
                CREATE TABLE IF NOT EXISTS approvals (
                    request_id TEXT PRIMARY KEY, scope TEXT, summary TEXT, risk TEXT,
                    state TEXT, approved_by TEXT, note TEXT, at TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_perm_subject ON permissions(subject);
                """
            )
            self._conn.commit()

    # ---------------- risk ----------------
    def classify(self, action: str, scope: Optional[str] = None) -> Dict[str, Any]:
        text = f"{scope or ''} {action or ''}".lower()
        risk = RISK_SAFE
        matched: List[str] = []
        for pattern, level in PROTECTED_PATTERNS:
            if re.search(pattern, text):
                matched.append(pattern)
                if RISK_ORDER[level] > RISK_ORDER[risk]:
                    risk = level
        if scope:
            # longest (most specific) prefix wins, then combine with pattern risk
            table = (
                ("system.", RISK_HIGH), ("files.delete", RISK_HIGH), ("files.read", RISK_LOW),
                ("files.", RISK_MEDIUM), ("process.kill", RISK_HIGH), ("process.", RISK_MEDIUM),
                ("network.read", RISK_LOW), ("network.", RISK_MEDIUM),
                ("browser.read", RISK_LOW), ("browser.", RISK_MEDIUM),
                ("code.write", RISK_HIGH), ("code.read", RISK_SAFE),
                ("memory.read", RISK_LOW), ("memory.write", RISK_LOW),
                ("notes.", RISK_SAFE), ("reminders.", RISK_SAFE), ("app.open", RISK_LOW),
            )
            matches = [(len(p), lvl) for p, lvl in table if scope.startswith(p)]
            if matches:
                scope_risk = max(matches, key=lambda m: m[0])[1]
                if RISK_ORDER[scope_risk] > RISK_ORDER[risk]:
                    risk = scope_risk
        return {"risk": risk, "protected": bool(matched), "patterns": matched}

    # ---------------- permissions ----------------
    def grant(self, subject: str, scope: str, granted_by: str = "owner", reason: str = "",
              ttl_seconds: Optional[float] = None) -> Permission:
        now = _utc()
        perm = Permission(
            scope=scope,
            granted_at=now.isoformat(),
            granted_by=granted_by,
            reason=reason,
            expires_at=(now + timedelta(seconds=ttl_seconds)).isoformat() if ttl_seconds else None,
        )
        with self._lock:
            self._conn.execute(
                "INSERT INTO permissions(perm_id, subject, scope, granted_at, expires_at, granted_by, reason, revoked)"
                " VALUES(?,?,?,?,?,?,?,0)",
                (perm.perm_id, subject, scope, perm.granted_at, perm.expires_at, granted_by, reason),
            )
            self._conn.commit()
        return perm

    def grant_temporary(self, subject: str, scope: str, ttl_seconds: float, **kw: Any) -> Permission:
        return self.grant(subject, scope, ttl_seconds=ttl_seconds, **kw)

    def revoke(self, perm_id: str) -> bool:
        with self._lock:
            cur = self._conn.execute("UPDATE permissions SET revoked=1 WHERE perm_id=?", (perm_id,))
            self._conn.commit()
            return cur.rowcount > 0

    def permissions(self, subject: str, include_expired: bool = False) -> List[Permission]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM permissions WHERE subject=? ORDER BY granted_at DESC", (subject,)
            ).fetchall()
        out = []
        for r in rows:
            p = Permission(r["scope"], r["granted_at"], r["granted_by"], r["reason"],
                           r["expires_at"], bool(r["revoked"]), r["perm_id"])
            if include_expired or p.is_active():
                out.append(p)
        return out

    def purge_expired(self) -> int:
        """Expired permissions are marked revoked so they cannot be resurrected."""
        now = _utc().isoformat()
        with self._lock:
            cur = self._conn.execute(
                "UPDATE permissions SET revoked=1 WHERE revoked=0 AND expires_at IS NOT NULL AND expires_at < ?",
                (now,),
            )
            self._conn.commit()
            return cur.rowcount

    # ---------------- decision ----------------
    def check(self, subject: str, scope: str, action: str = "", trace_id: Optional[str] = None) -> Decision:
        cls = self.classify(action, scope)
        risk, protected = cls["risk"], cls["protected"]
        reasons: List[str] = [f"risk={risk}"]
        perm = None
        for p in self.permissions(subject):
            if p.covers(scope):
                perm = p
                break
        expired = [p for p in self.permissions(subject, include_expired=True)
                   if p.covers(scope) and not p.is_active()]
        if perm is None and expired:
            reasons.append("matching permission expired or revoked")
        if protected and risk in (RISK_HIGH, RISK_CRITICAL):
            reasons.append("protected operation requires human approval")
            effect = "ask"
        elif perm is not None:
            reasons.append(f"granted scope {perm.scope} by {perm.granted_by}")
            effect = "allow" if RISK_ORDER[risk] < RISK_ORDER[RISK_CRITICAL] else "ask"
        elif RISK_ORDER[risk] >= RISK_ORDER[self.default_ask_from]:
            reasons.append("no permission and risk above ask threshold")
            effect = "ask"
        elif RISK_ORDER[risk] <= RISK_ORDER[RISK_LOW]:
            reasons.append("low risk default-allow")
            effect = "allow"
        else:
            effect = "deny"
        dec = Decision(effect, scope, risk, reasons, perm.perm_id if perm else None, protected)
        self.audit(subject=subject, command=action, scope=scope, decision=effect, risk=risk,
                   permission_id=dec.permission_id, result="pending", trace_id=trace_id)
        return dec

    # ---------------- approvals ----------------
    def set_approval_hook(self, hook) -> None:
        """GUI/CLI registers a callable(ApprovalRequest) to surface the prompt."""
        self._approval_hook = hook

    def request_approval(self, scope: str, summary: str, risk: str = RISK_HIGH,
                         timeout: float = 30.0, **details: Any) -> ApprovalRequest:
        req = ApprovalRequest(uuid.uuid4().hex[:10], scope, summary, risk, timeout, details)
        with self._lock:
            self.pending[req.request_id] = req
        if self._approval_hook:
            try:
                self._approval_hook(req)
            except Exception as exc:  # hook must never break the pipeline
                req.details["hook_error"] = str(exc)
        return req

    def resolve_approval(self, request_id: str, approved: bool, by: str = "user",
                         note: Optional[str] = None) -> Dict[str, Any]:
        with self._lock:
            req = self.pending.get(request_id)
        if req is None:
            raise KeyError(f"unknown approval {request_id}")
        req.resolve(approved, by, note)
        self._persist_approval(req)
        return req.to_dict()

    def wait_for_approval(self, req: ApprovalRequest) -> Dict[str, Any]:
        state = req.wait()
        self._persist_approval(req)
        with self._lock:
            self.pending.pop(req.request_id, None)
        return {"state": state, "approved": state == "approved", **req.to_dict()}

    def _persist_approval(self, req: ApprovalRequest) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO approvals(request_id, scope, summary, risk, state, approved_by, note, at)"
                " VALUES(?,?,?,?,?,?,?,?)",
                (req.request_id, req.scope, req.summary, req.risk, req.state, req.approved_by,
                 req.note, _utc().isoformat()),
            )
            self._conn.commit()

    def pending_approvals(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [r.to_dict() for r in self.pending.values() if r.state == "pending"]

    # ---------------- guard helper ----------------
    def guard(self, subject: str, scope: str, action: str = "", timeout: float = 30.0,
              trace_id: Optional[str] = None) -> Dict[str, Any]:
        """Single entry point used by managers: returns {allowed, ...}."""
        dec = self.check(subject, scope, action, trace_id=trace_id)
        if dec.effect == "allow":
            return {"allowed": True, "decision": dec.to_dict()}
        if dec.effect == "deny":
            return {"allowed": False, "decision": dec.to_dict(), "reason": "denied by policy"}
        req = self.request_approval(scope, action or scope, dec.risk, timeout)
        res = self.wait_for_approval(req)
        self.audit(subject=subject, command=action, scope=scope, decision=dec.effect,
                   risk=dec.risk, result=res["state"], trace_id=trace_id)
        return {"allowed": res["approved"], "decision": dec.to_dict(), "approval": res}

    # ---------------- audit (S24) ----------------
    def audit(self, subject: str, command: str = "", tool: str = "", scope: str = "",
              decision: str = "", risk: str = "", permission_id: Optional[str] = None,
              result: str = "", trace_id: Optional[str] = None, **extra: Any) -> Dict[str, Any]:
        row = {
            "trace_id": trace_id, "subject": subject, "command": redact(command), "tool": tool,
            "scope": scope, "decision": decision, "risk": risk, "permission_id": permission_id,
            "result": result, "at": _utc().isoformat(),
            "extra": json.dumps(redact(extra), default=str),
        }
        with self._lock:
            self._conn.execute(
                "INSERT INTO audit(trace_id, subject, command, tool, scope, decision, risk,"
                " permission_id, result, at, extra) VALUES(:trace_id,:subject,:command,:tool,"
                ":scope,:decision,:risk,:permission_id,:result,:at,:extra)",
                row,
            )
            self._conn.commit()
        return row

    def audit_log(self, limit: int = 50, subject: Optional[str] = None) -> List[Dict[str, Any]]:
        with self._lock:
            if subject:
                rows = self._conn.execute(
                    "SELECT * FROM audit WHERE subject=? ORDER BY id DESC LIMIT ?", (subject, limit)
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT * FROM audit ORDER BY id DESC LIMIT ?", (limit,)
                ).fetchall()
        return [dict(r) for r in rows]


_POLICY: Optional[PolicyEngine] = None
_PLOCK = threading.Lock()


def get_policy(db_path: Optional[str] = None) -> PolicyEngine:
    global _POLICY
    with _PLOCK:
        if _POLICY is None:
            _POLICY = PolicyEngine(db_path)
        return _POLICY
