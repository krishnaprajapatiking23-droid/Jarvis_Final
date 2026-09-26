"""Universal manager interface (roadmap section 16).

Every specialised manager implements the same contract -- ``capability``,
``can_handle``, ``execute``, ``verify``, ``rollback`` and ``health`` -- so the
manager registry can select, probe, fall back and roll back without knowing
anything about the individual manager.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

__all__ = ["BaseManager", "ManagerResult"]

log = logging.getLogger("jarvis.managers")


def ManagerResult(success: bool, reply: str = "", **extra: Any) -> Dict[str, Any]:
    """Uniform result envelope every manager returns."""
    result: Dict[str, Any] = {"success": bool(success), "reply": reply}
    result.update(extra)
    return result


class BaseManager:
    """Common behaviour for every specialised manager."""

    #: Short capability name used by the registry.
    capability = "generic"
    #: Human description shown by capability discovery.
    description = ""

    def can_handle(self, command: Any) -> bool:
        """True when this manager wants the command."""
        return False

    def execute(self, command: Any, **context: Any) -> Dict[str, Any]:
        """Perform the work. Must never raise: return a failure envelope."""
        return ManagerResult(False, "%s has no implementation." % self.capability)

    def verify(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Confirm the result actually happened."""
        if not isinstance(result, dict):
            return {"success": False, "message": "no result to verify"}
        return {"success": bool(result.get("success")),
                "message": result.get("reply", "")}

    def rollback(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Undo the work when it is reversible."""
        return {"success": False, "message": "%s is not reversible" % self.capability}

    def health(self) -> Dict[str, Any]:
        """Report whether this manager can run right now."""
        return {"available": True, "capability": self.capability, "detail": ""}

    # -- convenience -------------------------------------------------
    def safe_execute(self, command: Any, **context: Any) -> Dict[str, Any]:
        """execute() with a guaranteed envelope even on an exception."""
        try:
            outcome = self.execute(command, **context)
        except Exception as error:
            log.warning("%s failed on %r: %r", self.capability, command, error)
            return ManagerResult(
                False, "%s failed: %s" % (self.capability, error),
                error="%s: %s" % (type(error).__name__, error),
            )
        if not isinstance(outcome, dict):
            return ManagerResult(True, str(outcome))
        outcome.setdefault("success", True)
        outcome.setdefault("reply", "")
        return outcome
