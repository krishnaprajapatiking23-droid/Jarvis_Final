"""Browser agent: opens sites and runs searches in the default browser."""

from __future__ import annotations

import re
from typing import Any, Dict

from brains_v2.agents.base import Agent, AgentResult

__all__ = ["BrowserAgent", "browser_agent"]

TRIGGERS = re.compile(r"\b(browse|website|google|youtube|search the web|open site|url|https?://)\b", re.IGNORECASE)


class BrowserAgent(Agent):
    name = "browser"
    capability = "browser"
    description = "Browser agent: opens sites and runs searches in the default browser."

    def can_handle(self, goal: str) -> bool:
        return bool(TRIGGERS.search(str(goal or "")))

    def act(self, step: Dict[str, Any], goal: str,
            context: Dict[str, Any]) -> Dict[str, Any]:
        try:
            from automation.browser import open_website
        except Exception as error:
            return AgentResult(False, "Browser control unavailable: %s" % error)

        outcome = open_website(goal)
        if not outcome:
            return AgentResult(False, "I couldn't work out which site you meant.")
        return AgentResult(True, str(outcome))

browser_agent = BrowserAgent()
