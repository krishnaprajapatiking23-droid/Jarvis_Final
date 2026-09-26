"""Memory tool for the brain's tool registry.

Adapter over the memory manager so tool callers and the router share one
memory implementation.
"""

from __future__ import annotations

from typing import Any, Dict

from brains_v2.managers.memory_manager import memory_manager

__all__ = ["MemoryTool", "memory_tool"]


class MemoryTool:
    name = "memory"
    description = "Stores and recalls facts about the user."

    def can_handle(self, command: Any) -> bool:
        return memory_manager.can_handle(command)

    def execute(self, command: Any) -> Dict[str, Any]:
        return memory_manager.safe_execute(command)


memory_tool = MemoryTool()
