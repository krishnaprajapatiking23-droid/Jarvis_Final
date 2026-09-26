"""Desktop agent: opens, closes and controls applications, then verifies it worked."""

from __future__ import annotations

import re
from typing import Any, Dict

from brains_v2.agents.base import Agent, AgentResult

__all__ = ["DesktopAgent", "desktop_agent"]

TRIGGERS = re.compile(r"\b(open|close|launch|start|quit|minimi[sz]e|maximi[sz]e|screenshot)\b", re.IGNORECASE)


class DesktopAgent(Agent):
    name = "desktop"
    capability = "automation"
    description = "Desktop agent: opens, closes and controls applications, then verifies it worked."

    def can_handle(self, goal: str) -> bool:
        return bool(TRIGGERS.search(str(goal or "")))

    def act(self, step: Dict[str, Any], goal: str,
            context: Dict[str, Any]) -> Dict[str, Any]:
        from brains_v2.managers.automation_manager import automation_manager

        if not automation_manager.can_handle(goal):
            return AgentResult(False, "No application was named.")

        outcome = automation_manager.safe_execute(goal)
        checked = automation_manager.verify(outcome)
        return AgentResult(bool(checked.get("success")),
                           outcome.get("reply", ""), verification=checked)

desktop_agent = DesktopAgent()
