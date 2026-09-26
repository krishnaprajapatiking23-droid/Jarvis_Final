"""Automation manager (roadmap section 12).

Wraps the real desktop automation helpers behind the universal interface and
adds verification: after opening an application it checks that the process is
actually running instead of assuming success.
"""

from __future__ import annotations

import re
from typing import Any, Dict

from brains_v2.managers.base import BaseManager, ManagerResult

__all__ = ["AutomationManager", "automation_manager"]

_ACTION = re.compile(r"\b(open|launch|start|run|close|quit|exit|kill|stop)\b",
                     re.IGNORECASE)


class AutomationManager(BaseManager):
    capability = "automation"
    description = "Opens, closes and controls desktop applications."

    def can_handle(self, command: Any) -> bool:
        text = str(command or "")
        if not _ACTION.search(text):
            return False
        try:
            from automation.apps import match_app

            return bool(match_app(text))
        except Exception:
            return False

    def execute(self, command: Any, **context: Any) -> Dict[str, Any]:
        from automation.apps import close_app, is_close_request, match_app, open_app

        text = str(command or "")
        target = match_app(text)

        if not target:
            return ManagerResult(False, "I couldn't tell which application you meant.")

        if is_close_request(text):
            outcome = close_app(text)
            action = "close"
        else:
            outcome = open_app(text)
            action = "open"

        reply = outcome if isinstance(outcome, str) else str(outcome)
        return ManagerResult(True, reply, app=target, action=action, raw=outcome)

    def verify(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Check the process really is (or is no longer) running."""
        app = result.get("app")
        action = result.get("action")

        if not app or not action:
            return super().verify(result)

        try:
            import psutil
        except Exception:
            return {"success": bool(result.get("success")),
                    "message": "psutil not installed; cannot verify"}

        needle = str(app).lower()
        running = any(needle in (p.name() or "").lower()
                      for p in psutil.process_iter(["name"]))

        expected = running if action == "open" else not running
        return {
            "success": expected,
            "message": "%s is %srunning" % (app, "" if running else "not "),
        }

    def rollback(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Opening is undone by closing, and vice versa."""
        from automation.apps import close_app, open_app

        app = result.get("app")
        if not app:
            return {"success": False, "message": "nothing to roll back"}

        try:
            if result.get("action") == "open":
                close_app(str(app))
            else:
                open_app(str(app))
        except Exception as error:
            return {"success": False, "message": str(error)}

        return {"success": True, "message": "rolled back %s" % app}

    def health(self) -> Dict[str, Any]:
        try:
            from automation.apps import match_app  # noqa: F401
        except Exception as error:
            return {"available": False, "capability": self.capability,
                    "detail": "%s: %s" % (type(error).__name__, error)}
        return {"available": True, "capability": self.capability, "detail": ""}


automation_manager = AutomationManager()
