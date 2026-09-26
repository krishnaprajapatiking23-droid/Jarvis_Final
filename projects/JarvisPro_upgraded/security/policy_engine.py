"""
==========================================
JARVIS PRO
Policy & permission engine
==========================================

Roadmap section 11, plus the "real confirmation" behaviour from Mark-LII:
the model can never confirm its own irreversible action - a human must.

Usage:

    from security.policy_engine import policy

    decision = policy.check("file.delete", {"path": "C:/Windows"})

    if decision.allowed:
        ...
    elif decision.needs_confirmation:
        token = policy.request(decision)      # show to the user
        ...
        policy.confirm(token)                 # only a human calls this

Modes (``policy.mode`` setting): ``allow`` | ``ask`` | ``deny``.
"""

from __future__ import annotations

import re
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from config import config
from core.observability import observability


LOW = "low"
MEDIUM = "medium"
HIGH = "high"
CRITICAL = "critical"


# Action -> risk. Matched as a prefix, so "file.delete.folder" inherits
# the rule of "file.delete".
RISK_RULES: dict[str, str] = {
    # read-only
    "read": LOW,
    "search": LOW,
    "memory.read": LOW,
    "system.info": LOW,
    "screen.capture": LOW,
    "web.search": LOW,
    "app.open": LOW,
    # normal writes
    "file.write": MEDIUM,
    "file.create": MEDIUM,
    "file.move": MEDIUM,
    "file.copy": MEDIUM,
    "memory.write": MEDIUM,
    "app.close": MEDIUM,
    "clipboard": MEDIUM,
    "message.send": MEDIUM,
    "browser.automate": MEDIUM,
    # destructive / irreversible
    "file.delete": HIGH,
    "folder.delete": HIGH,
    "process.kill": HIGH,
    "settings.change": HIGH,
    "network.change": HIGH,
    "code.execute": HIGH,
    "shell": HIGH,
    "self.modify": HIGH,
    # never without a human
    "system.shutdown": CRITICAL,
    "system.restart": CRITICAL,
    "disk.format": CRITICAL,
    "security.disable": CRITICAL,
    "credentials": CRITICAL,
}


# Paths that are never writable, whatever the mode.
PROTECTED_PATTERNS = [
    re.compile(r"^[a-z]:[\\/]windows", re.IGNORECASE),
    re.compile(r"^[a-z]:[\\/]program files", re.IGNORECASE),
    re.compile(r"^/(bin|sbin|usr|etc|boot|dev|proc|sys)(/|$)", re.IGNORECASE),
    re.compile(r"(^|[\\/])(system32|syswow64)([\\/]|$)", re.IGNORECASE),
    re.compile(r"(^|[\\/])\.ssh([\\/]|$)", re.IGNORECASE),
    re.compile(r"api_keys\.json$", re.IGNORECASE),
    re.compile(r"(^|[\\/])\.env$", re.IGNORECASE),
]


@dataclass
class Decision:
    action: str
    risk: str
    allowed: bool
    needs_confirmation: bool
    reason: str
    details: dict[str, Any] = field(default_factory=dict)

    def report(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "risk": self.risk,
            "allowed": self.allowed,
            "needs_confirmation": self.needs_confirmation,
            "reason": self.reason,
            "details": self.details,
        }


class PolicyEngine:

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._pending: dict[str, dict[str, Any]] = {}
        self._grants: dict[str, float] = {}
        self._audit: list[dict[str, Any]] = []

    # ---------------------------------------------------- classification

    def mode(self) -> str:
        value = str(config.get("policy.mode", "ask")).strip().lower()

        return value if value in ("allow", "ask", "deny") else "ask"

    def risk(self, action: str) -> str:
        """Risk class of an action name such as ``file.delete``."""

        name = str(action or "").strip().lower()

        best = LOW
        best_length = -1

        for prefix, level in RISK_RULES.items():
            if name == prefix or name.startswith(prefix + ".") or prefix in name:
                if len(prefix) > best_length:
                    best = level
                    best_length = len(prefix)

        return best if best_length >= 0 else MEDIUM

    def protected(self, path: str) -> bool:
        """True when a path must never be modified."""

        text = str(path or "").strip()

        if not text:
            return False

        return any(pattern.search(text) for pattern in PROTECTED_PATTERNS)

    # ---------------------------------------------------- checking

    def check(self, action: str, details: dict[str, Any] | None = None) -> Decision:
        details = dict(details or {})
        risk = self.risk(action)
        mode = self.mode()

        path = str(details.get("path") or details.get("target") or "")

        if path and self.protected(path) and risk != LOW:
            decision = Decision(
                action,
                CRITICAL,
                False,
                False,
                "protected system path - refused",
                details,
            )

            self._record(decision)

            return decision

        if self._granted(action):
            decision = Decision(
                action,
                risk,
                True,
                False,
                "temporary permission granted earlier",
                details,
            )

            self._record(decision)

            return decision

        if mode == "deny" and risk != LOW:
            decision = Decision(action, risk, False, False, "policy mode is deny", details)

        elif risk == CRITICAL:
            decision = Decision(
                action,
                risk,
                False,
                True,
                "irreversible action - a human must confirm",
                details,
            )

        elif risk == HIGH and (mode == "ask" or config.get("agent.confirm_risky", True)):
            decision = Decision(
                action,
                risk,
                False,
                True,
                "destructive action - confirmation required",
                details,
            )

        else:
            decision = Decision(action, risk, True, False, "allowed by policy", details)

        self._record(decision)

        return decision

    def allowed(self, action: str, details: dict[str, Any] | None = None) -> bool:
        """Shorthand for guards inside tools."""

        return self.check(action, details).allowed

    # ---------------------------------------------------- confirmation

    def request(self, decision: Decision, ttl: float = 300.0) -> str:
        """Create a confirmation token the UI shows to the user."""

        token = uuid.uuid4().hex[:10]

        with self._lock:
            self._pending[token] = {
                "action": decision.action,
                "risk": decision.risk,
                "details": decision.details,
                "reason": decision.reason,
                "expires": time.time() + ttl,
                "confirmed": False,
            }

        observability.info(
            "policy",
            "confirmation requested",
            action=decision.action,
            risk=decision.risk,
            token=token,
        )

        return token

    def pending(self) -> list[dict[str, Any]]:
        now = time.time()

        with self._lock:
            return [
                dict(item, token=token)
                for token, item in self._pending.items()
                if item["expires"] > now and not item["confirmed"]
            ]

    def confirm(self, token: str, approved: bool = True) -> bool:
        """Called ONLY from a human action in the UI / CLI."""

        with self._lock:
            item = self._pending.get(token)

            if not item or item["expires"] < time.time():
                return False

            item["confirmed"] = bool(approved)

        observability.info(
            "policy",
            "confirmation answered",
            token=token,
            approved=bool(approved),
        )

        return bool(approved)

    def is_confirmed(self, token: str) -> bool:
        with self._lock:
            item = self._pending.get(token)

            return bool(item and item["confirmed"] and item["expires"] > time.time())

    # ---------------------------------------------------- grants

    def grant(self, action: str, seconds: float = 600.0) -> None:
        """Temporary permission with an expiry (roadmap: temp permissions)."""

        with self._lock:
            self._grants[str(action).strip().lower()] = time.time() + seconds

    def revoke(self, action: str = "") -> None:
        with self._lock:
            if action:
                self._grants.pop(str(action).strip().lower(), None)
            else:
                self._grants.clear()

    def _granted(self, action: str) -> bool:
        name = str(action).strip().lower()
        now = time.time()

        with self._lock:
            for granted, expires in list(self._grants.items()):
                if expires < now:
                    del self._grants[granted]
                    continue

                if name == granted or name.startswith(granted + "."):
                    return True

        return False

    # ---------------------------------------------------- audit

    def _record(self, decision: Decision) -> None:
        entry = dict(decision.report(), at=time.time())

        with self._lock:
            self._audit.append(entry)
            del self._audit[:-500]

        if decision.risk in (HIGH, CRITICAL) or not decision.allowed:
            observability.log(
                "warning" if not decision.allowed else "info",
                "policy",
                f"{decision.action}: {decision.reason}",
                risk=decision.risk,
            )

    def audit(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._audit[-limit:])


policy = PolicyEngine()
