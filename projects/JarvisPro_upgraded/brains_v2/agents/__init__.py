"""Agent registry (roadmap section 18).

Every agent import is guarded so one broken optional dependency cannot take
the registry down.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from brains_v2.agents.base import Agent, AgentResult

log = logging.getLogger("jarvis.agents")

__all__ = ["Agent", "AgentResult", "AGENTS", "get", "names", "select", "run"]

AGENTS: Dict[str, Agent] = {}

for _module, _attribute in (
    ("memory", "memory_agent"),
    ("desktop", "desktop_agent"),
    ("browser", "browser_agent"),
    ("research", "research_agent"),
    ("coding", "coding_agent"),
    ("vision", "vision_agent"),
    ("conversation", "conversation_agent"),
    ("business", "business_agent"),
):
    try:
        _imported = __import__("brains_v2.agents." + _module, fromlist=[_attribute])
        _agent = getattr(_imported, _attribute)
        AGENTS[_agent.name] = _agent
    except Exception as _error:
        log.info("agent %s unavailable: %s", _module, _error)


def get(name: str) -> Optional[Agent]:
    return AGENTS.get(name)


def names() -> List[str]:
    return sorted(AGENTS)


def select(goal: str) -> Optional[Agent]:
    """First agent that claims the goal; conversation is the last resort."""
    for name, candidate in AGENTS.items():
        if name == "conversation":
            continue
        try:
            if candidate.can_handle(goal):
                return candidate
        except Exception:
            continue
    return AGENTS.get("conversation")


def run(goal: str, **kwargs: Any) -> Dict[str, Any]:
    chosen = select(goal)
    if chosen is None:
        return AgentResult(False, "No agent is available.")
    return chosen.run(goal, **kwargs)
