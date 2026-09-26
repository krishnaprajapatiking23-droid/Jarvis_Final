"""
==========================================
JARVIS PRO
Conversation State
==========================================

The single structured description of "where the conversation is right now".
Every pipeline stage reads from it and the engine writes it back to
``data/conversation.db`` after each relevant turn.

This is deliberately a plain dataclass with dict serialisation so it can be
persisted, logged and diffed without any framework.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

MAX_RECENT_ENTITIES = 12


@dataclass
class ConversationState:
    """Mutable state of one conversation."""

    session_id: str = ""
    conversation_id: str = ""
    turn: int = 0

    current_topic: str = ""
    previous_topic: str = ""

    # active_entities: entities referred to by the newest turn.
    # recent_entities: rolling window used for reference resolution.
    active_entities: List[Dict[str, Any]] = field(default_factory=list)
    recent_entities: List[Dict[str, Any]] = field(default_factory=list)

    conversation_goal: str = ""
    last_user_intent: str = ""
    last_jarvis_action: str = ""
    last_user_message: str = ""
    last_jarvis_reply: str = ""

    pending_question: str = ""
    pending_action: Optional[Dict[str, Any]] = None

    # resolved reference word -> entity name, e.g. {"it": "chrome"}
    user_references: Dict[str, str] = field(default_factory=dict)

    emotion: str = "neutral"
    style: str = "balanced"
    language: str = "en"

    temporal: Optional[Dict[str, Any]] = None
    summary: str = ""
    updated_at: str = ""

    # ------------------------------------------------------------------
    # entities
    # ------------------------------------------------------------------
    def remember_entities(self, found: List[Dict[str, Any]]) -> None:
        """Mark ``found`` as active and push them onto the recent window."""
        if not found:
            self.active_entities = []
            return

        self.active_entities = list(found)

        for entity in found:
            name = str(entity.get("name", "")).strip()
            if not name:
                continue
            self.recent_entities = [
                existing
                for existing in self.recent_entities
                if str(existing.get("name", "")).lower() != name.lower()
            ]
            self.recent_entities.insert(0, dict(entity))

        del self.recent_entities[MAX_RECENT_ENTITIES:]

    def last_entity(self, type: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Most recently mentioned entity, optionally filtered by type."""
        for entity in self.recent_entities:
            if type is None or entity.get("type") == type:
                return entity
        return None

    def entities_of_type(self, type: str) -> List[Dict[str, Any]]:
        return [e for e in self.recent_entities if e.get("type") == type]

    # ------------------------------------------------------------------
    # topics
    # ------------------------------------------------------------------
    def set_topic(self, topic: str) -> bool:
        """Update the active topic. Returns True when the topic changed."""
        topic = (topic or "").strip()
        if not topic or topic == self.current_topic:
            return False
        if self.current_topic:
            self.previous_topic = self.current_topic
        self.current_topic = topic
        return True

    # ------------------------------------------------------------------
    # pending question / action
    # ------------------------------------------------------------------
    def ask(self, question: str, action: Optional[Dict[str, Any]] = None) -> None:
        self.pending_question = question
        self.pending_action = action

    def clear_pending(self) -> None:
        self.pending_question = ""
        self.pending_action = None

    @property
    def is_waiting(self) -> bool:
        return bool(self.pending_question or self.pending_action)

    # ------------------------------------------------------------------
    # serialisation
    # ------------------------------------------------------------------
    def touch(self) -> None:
        self.updated_at = datetime.now().isoformat(timespec="seconds")

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "ConversationState":
        """Rebuild state from persisted data, ignoring unknown/absent keys."""
        state = cls()
        if not isinstance(data, dict):
            return state
        valid = set(state.to_dict().keys())
        for key, value in data.items():
            if key in valid and value is not None:
                setattr(state, key, value)
        return state

    def describe(self) -> str:
        """Compact human/LLM readable description of the state."""
        lines: List[str] = []
        if self.current_topic:
            lines.append(f"Current topic: {self.current_topic}")
        if self.previous_topic and self.previous_topic != self.current_topic:
            lines.append(f"Previous topic: {self.previous_topic}")
        if self.recent_entities:
            named = ", ".join(
                f"{e.get('name')} ({e.get('type')})" for e in self.recent_entities[:6]
            )
            lines.append(f"Recent entities: {named}")
        if self.last_user_intent:
            lines.append(f"Last intent: {self.last_user_intent}")
        if self.last_jarvis_action:
            lines.append(f"Last action: {self.last_jarvis_action}")
        if self.pending_question:
            lines.append(f"Awaiting answer to: {self.pending_question}")
        if self.emotion and self.emotion != "neutral":
            lines.append(f"User emotion: {self.emotion}")
        if self.style and self.style != "balanced":
            lines.append(f"Preferred style: {self.style}")
        return "\n".join(lines)


__all__ = ["ConversationState", "MAX_RECENT_ENTITIES"]
