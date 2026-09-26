"""System tool for the brain's tool registry.

Adapter over :mod:`tools.system` so there is one telemetry implementation.
"""

from __future__ import annotations

from typing import Any, Dict

from tools.system import system_tool as _backend

__all__ = ["SystemTool", "system_tool"]


class SystemTool:
    name = "system"
    description = "CPU, memory, disk and platform information."

    def can_handle(self, command: Any) -> bool:
        text = str(command or "").lower()
        return any(word in text for word in
                   ("system info", "system information", "cpu", "ram",
                    "memory usage", "disk space", "how much memory"))

    def execute(self, command: Any = "") -> Dict[str, Any]:
        return {"success": True, "reply": _backend.summary(),
                "data": _backend.report()}


system_tool = SystemTool()
