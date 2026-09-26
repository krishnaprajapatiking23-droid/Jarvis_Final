"""Tool manager (roadmap section 1: Tool Registry).

Owns tool registration, capability lookup and guarded execution so no caller
has to reach into a tool module directly.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional

from brains_v2.managers.base import BaseManager, ManagerResult

__all__ = ["ToolManager", "tool_manager"]

log = logging.getLogger("jarvis.tools")


class ToolManager(BaseManager):
    capability = "tools"
    description = "Registry and guarded execution for callable tools."

    def __init__(self) -> None:
        self._tools: Dict[str, Dict[str, Any]] = {}
        self._bootstrapped = False

    # -- registry ----------------------------------------------------
    def register(self, name: str, handler: Callable[..., Any],
                 description: str = "", **meta: Any) -> None:
        if not callable(handler):
            raise TypeError("tool %r is not callable" % name)
        self._tools[name] = {"handler": handler, "description": description,
                             "meta": meta, "calls": 0, "failures": 0}

    def unregister(self, name: str) -> bool:
        return self._tools.pop(name, None) is not None

    def names(self) -> List[str]:
        self.bootstrap()
        return sorted(self._tools)

    def describe(self) -> List[Dict[str, str]]:
        self.bootstrap()
        return [{"name": name, "description": entry["description"]}
                for name, entry in sorted(self._tools.items())]

    def bootstrap(self) -> None:
        """Register the built-in tools once."""
        if self._bootstrapped:
            return
        self._bootstrapped = True

        try:
            from tools.datetime_tool import datetime_tool

            self.register("datetime", datetime_tool.execute,
                          datetime_tool.description)
        except Exception as error:
            log.debug("datetime tool unavailable: %s", error)

        try:
            from tools.system import system_tool

            self.register("system", lambda *_a, **_k: system_tool.report(),
                          system_tool.description)
        except Exception as error:
            log.debug("system tool unavailable: %s", error)

        try:
            from tools.file_tool import file_tool

            self.register("file_read", file_tool.read, "Read a workspace file.")
            self.register("file_write", file_tool.write, "Write a workspace file.")
            self.register("file_list", file_tool.list, "List a workspace folder.")
        except Exception as error:
            log.debug("file tool unavailable: %s", error)

        try:
            from tools.search import search_tool

            self.register("search", search_tool.execute,
                          search_tool.description)
        except Exception as error:
            log.debug("search tool unavailable: %s", error)

    # -- execution ---------------------------------------------------
    def execute_tool(self, name: str, *args: Any, **kwargs: Any) -> Dict[str, Any]:
        self.bootstrap()
        entry = self._tools.get(name)

        if entry is None:
            return ManagerResult(False, "No tool called %r." % name,
                                 available=self.names())

        entry["calls"] += 1
        try:
            outcome = entry["handler"](*args, **kwargs)
        except Exception as error:
            entry["failures"] += 1
            log.warning("tool %s failed: %r", name, error)
            return ManagerResult(False, "Tool %s failed: %s" % (name, error))

        if isinstance(outcome, dict):
            outcome.setdefault("success", True)
            return outcome

        return ManagerResult(True, str(outcome), result=outcome)

    def statistics(self) -> Dict[str, Dict[str, int]]:
        return {name: {"calls": entry["calls"], "failures": entry["failures"]}
                for name, entry in self._tools.items()}

    def can_handle(self, command: Any) -> bool:
        self.bootstrap()
        for entry in self._tools.values():
            handler = entry["handler"]
            owner = getattr(handler, "__self__", None)
            if owner is not None and hasattr(owner, "can_handle"):
                try:
                    if owner.can_handle(command):
                        return True
                except Exception:
                    continue
        return False

    def execute(self, command: Any, **context: Any) -> Dict[str, Any]:
        self.bootstrap()
        for name, entry in self._tools.items():
            owner = getattr(entry["handler"], "__self__", None)
            if owner is None or not hasattr(owner, "can_handle"):
                continue
            try:
                if owner.can_handle(command):
                    return self.execute_tool(name, command)
            except Exception:
                continue
        return ManagerResult(False, "", handled=False)

    def health(self) -> Dict[str, Any]:
        self.bootstrap()
        return {"available": bool(self._tools), "capability": self.capability,
                "detail": "%d tool(s) registered" % len(self._tools)}


tool_manager = ToolManager()
