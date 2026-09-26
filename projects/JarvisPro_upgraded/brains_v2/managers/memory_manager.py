"""Memory manager (roadmap section 4).

Adapter over the memory implementation that is actually wired into the brain,
exposed through the universal manager interface so the registry can use it.
"""

from __future__ import annotations

import re
from typing import Any, Dict

from brains_v2.managers.base import BaseManager, ManagerResult

__all__ = ["MemoryManager", "memory_manager"]

_REMEMBER = re.compile(r"^\s*(?:please\s+)?remember\s+(?P<fact>.+)$", re.IGNORECASE)
_RECALL = re.compile(r"\b(?:what|who|when|where)\b.*\b(?:my|our)\b", re.IGNORECASE)
_FORGET = re.compile(r"^\s*(?:please\s+)?forget\s+(?P<fact>.+)$", re.IGNORECASE)


class MemoryManager(BaseManager):
    capability = "memory"
    description = "Stores, recalls, corrects and forgets facts about the user."

    def can_handle(self, command: Any) -> bool:
        text = str(command or "")
        return bool(_REMEMBER.match(text) or _FORGET.match(text) or _RECALL.search(text))

    def execute(self, command: Any, **context: Any) -> Dict[str, Any]:
        from memory.memory_engine import process_memory

        answer = process_memory(str(command or ""))

        if not answer:
            return ManagerResult(False, "", handled=False)

        return ManagerResult(True, answer, handled=True)

    def health(self) -> Dict[str, Any]:
        try:
            import memory.memory_engine  # noqa: F401
        except Exception as error:
            return {"available": False, "capability": self.capability,
                    "detail": "%s: %s" % (type(error).__name__, error)}
        return {"available": True, "capability": self.capability, "detail": ""}


memory_manager = MemoryManager()
