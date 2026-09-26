"""Conversation agent: handles plain talk through the conversation engine."""

from __future__ import annotations

import re
from typing import Any, Dict

from brains_v2.agents.base import Agent, AgentResult

__all__ = ["ConversationAgent", "conversation_agent"]

TRIGGERS = re.compile(r"\b(hello|hi|thanks|thank you|how are you|goodbye|bye|talk)\b", re.IGNORECASE)


class ConversationAgent(Agent):
    name = "conversation"
    capability = "conversation"
    description = "Conversation agent: handles plain talk through the conversation engine."

    def can_handle(self, goal: str) -> bool:
        return bool(TRIGGERS.search(str(goal or "")))

    def act(self, step: Dict[str, Any], goal: str,
            context: Dict[str, Any]) -> Dict[str, Any]:
        from brains_v2.ai.conversation import conversation_adapter

        understanding = conversation_adapter.understand(goal)
        if understanding.get("handled"):
            return AgentResult(True, understanding.get("handled_reply", ""))
        return AgentResult(True, conversation_adapter.reply(goal, "", "chat"))

conversation_agent = ConversationAgent()
