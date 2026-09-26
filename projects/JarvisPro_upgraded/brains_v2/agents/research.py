"""Research agent: multi-source investigation with provenance, via jarvis_core."""

from __future__ import annotations

import re
from typing import Any, Dict

from brains_v2.agents.base import Agent, AgentResult

__all__ = ["ResearchAgent", "research_agent"]

TRIGGERS = re.compile(r"\b(research|investigate|find out|look up|compare sources|evidence)\b", re.IGNORECASE)


class ResearchAgent(Agent):
    name = "research"
    capability = "research"
    description = "Research agent: multi-source investigation with provenance, via jarvis_core."

    def can_handle(self, goal: str) -> bool:
        return bool(TRIGGERS.search(str(goal or "")))

    def act(self, step: Dict[str, Any], goal: str,
            context: Dict[str, Any]) -> Dict[str, Any]:
        from brains_v2.core_bridge import handle_research

        outcome = handle_research(goal)
        if outcome:
            return AgentResult(True, outcome["reply"])
        return AgentResult(
            False,
            "No research backend is configured, so I won't invent sources.")

research_agent = ResearchAgent()
