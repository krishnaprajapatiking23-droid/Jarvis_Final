"""Business agent: structures a business question into a checkable plan."""

from __future__ import annotations

import re
from typing import Any, Dict

from brains_v2.agents.base import Agent, AgentResult

__all__ = ["BusinessAgent", "business_agent"]

TRIGGERS = re.compile(r"\b(business|market|revenue|profit|pricing|customers?|competitor)\b", re.IGNORECASE)


class BusinessAgent(Agent):
    name = "business"
    capability = "business"
    description = "Business agent: structures a business question into a checkable plan."

    def can_handle(self, goal: str) -> bool:
        return bool(TRIGGERS.search(str(goal or "")))

    def act(self, step: Dict[str, Any], goal: str,
            context: Dict[str, Any]) -> Dict[str, Any]:
        from brains_v2.ai.planner import planner

        built = planner.create(goal)
        return AgentResult(True, planner.render(built), plan=built)

business_agent = BusinessAgent()
