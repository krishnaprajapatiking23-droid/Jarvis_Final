"""Vision agent: reads what is on screen, or says why it cannot."""

from __future__ import annotations

import re
from typing import Any, Dict

from brains_v2.agents.base import Agent, AgentResult

__all__ = ["VisionAgent", "vision_agent"]

TRIGGERS = re.compile(r"\b(screen|screenshot|ocr|read the screen|what.s on my screen|image)\b", re.IGNORECASE)


class VisionAgent(Agent):
    name = "vision"
    capability = "vision"
    description = "Vision agent: reads what is on screen, or says why it cannot."

    def can_handle(self, goal: str) -> bool:
        return bool(TRIGGERS.search(str(goal or "")))

    def act(self, step: Dict[str, Any], goal: str,
            context: Dict[str, Any]) -> Dict[str, Any]:
        from brains_v2.core_bridge import handle_vision

        outcome = handle_vision(goal)
        reply = outcome.get("reply", "")
        worked = "unavailable" not in reply.lower()
        return AgentResult(worked, reply)

vision_agent = VisionAgent()
