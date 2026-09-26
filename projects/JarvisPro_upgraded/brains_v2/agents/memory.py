"""Memory agent: stores, recalls and corrects facts on the user's behalf."""

from __future__ import annotations

import re
from typing import Any, Dict

from brains_v2.agents.base import Agent, AgentResult

__all__ = ["MemoryAgent", "memory_agent"]

TRIGGERS = re.compile(r"\b(remember|recall|forget|what do you know|my name|my favourite)\b", re.IGNORECASE)


class MemoryAgent(Agent):
    name = "memory"
    capability = "memory"
    description = "Memory agent: stores, recalls and corrects facts on the user's behalf."

    def can_handle(self, goal: str) -> bool:
        return bool(TRIGGERS.search(str(goal or "")))

    def act(self, step: Dict[str, Any], goal: str,
            context: Dict[str, Any]) -> Dict[str, Any]:
        from brains_v2.managers.memory_manager import memory_manager

        outcome = memory_manager.safe_execute(goal)
        return AgentResult(bool(outcome.get("success")),
                           outcome.get("reply", ""), raw=outcome)

memory_agent = MemoryAgent()
