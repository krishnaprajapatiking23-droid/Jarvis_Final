"""Permission checks for the legacy brain (roadmap section 11).

Delegates to ``jarvis_core.policy.PolicyEngine`` -- the engine the kernel and
the test suite already use -- so there is one set of rules, not two.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

__all__ = ["PermissionGate", "permission_gate", "check", "RISK_ORDER"]

log = logging.getLogger("jarvis.security.permission")

RISK_ORDER = ("low", "medium", "high", "critical")


class PermissionGate:
    """Ask / allow / deny decisions for a named action scope."""

    def __init__(self, subject: str = "owner"):
        self.subject = subject
        self._policy = None

    def policy(self) -> Optional[Any]:
        if self._policy is None:
            try:
                from jarvis_core.kernel import get_kernel

                self._policy = get_kernel().policy
            except Exception as error:
                log.info("policy engine unavailable: %s", error)
                return None
        return self._policy

    def classify(self, action: str, scope: str = "") -> Dict[str, Any]:
        engine = self.policy()
        if engine is None:
            return {"risk": "medium", "detail": "policy engine unavailable"}
        try:
            return engine.classify(action, scope or None)
        except Exception as error:
            return {"risk": "medium", "detail": str(error)}

    def check(self, scope: str, action: str = "") -> Dict[str, Any]:
        """Return {allowed, reason, risk} for this subject and scope."""
        engine = self.policy()

        if engine is None:
            return {"allowed": True, "reason": "policy engine unavailable",
                    "risk": "unknown"}

        try:
            decision = engine.check(self.subject, scope, action)
        except Exception as error:
            return {"allowed": False, "reason": str(error), "risk": "unknown"}

        allowed = getattr(decision, "allowed", None)
        if callable(allowed):
            allowed = allowed()
        if allowed is None:
            allowed = bool(getattr(decision, "allow", True))

        return {
            "allowed": bool(allowed),
            "reason": getattr(decision, "reason", ""),
            "risk": getattr(decision, "risk", "medium"),
        }

    def require(self, scope: str, action: str = "") -> bool:
        return bool(self.check(scope, action).get("allowed"))


permission_gate = PermissionGate()


def check(scope: str, action: str = "") -> Dict[str, Any]:
    return permission_gate.check(scope, action)
