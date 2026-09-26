"""
==========================================
JARVIS PRO
Conversation Session Manager  (features 3.16, 3.17)
==========================================

Owns the lifecycle of a conversation session:

    session_id, start time, end time, messages, active topic,
    context, entities and state

A session ends when the user says goodbye or after an idle timeout, and a
new one starts on the next message.  Multiple sessions never share state,
but a new session can deliberately resume the previous one
("continue from where we stopped").

This is a separate concern from ``session.session_manager``, which tracks
the *application* session (apps opened, folders created).  That module is
left untouched and is updated in parallel by the engine.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from conversation import store
from conversation.conversation_state import ConversationState

log = logging.getLogger("jarvis.conversation.session")

# Idle gap after which the next message starts a fresh session.
IDLE_TIMEOUT_MINUTES = 30

RESUME_PHRASES = (
    "continue from where we stopped",
    "continue where we left off",
    "continue from where we left",
    "where were we",
    "back to what we were saying",
    "resume our conversation",
    "continue our conversation",
    "what were we talking about",
    "as we were discussing",
    "continue previous conversation",
)


def new_session_id() -> str:
    return f"s-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"


def new_conversation_id() -> str:
    return f"c-{uuid.uuid4().hex[:10]}"


class SessionManager:
    """Creates, resumes, persists and closes conversation sessions."""

    def __init__(self, mode: str = "text", user: str = "") -> None:
        self.mode = mode
        self.user = user
        self.session_id: str = ""
        self.conversation_id: str = ""
        self.started_at: Optional[datetime] = None
        self.last_active: Optional[datetime] = None
        self.turn: int = 0

    # ------------------------------------------------------------------
    def is_resume_request(self, text: str) -> bool:
        lowered = (text or "").lower()
        return any(phrase in lowered for phrase in RESUME_PHRASES)

    # ------------------------------------------------------------------
    def idle_expired(self) -> bool:
        if not self.last_active:
            return False
        gap = (datetime.now() - self.last_active).total_seconds() / 60.0
        return gap > IDLE_TIMEOUT_MINUTES

    # ------------------------------------------------------------------
    def ensure(self, user: str = "", mode: str = "") -> str:
        """Return the active session id, starting a session when needed."""
        if self.session_id and not self.idle_expired():
            self.last_active = datetime.now()
            return self.session_id
        return self.start(user or self.user, mode or self.mode)

    # ------------------------------------------------------------------
    def start(self, user: str = "", mode: str = "") -> str:
        """Begin a new conversation session."""
        self.user = user or self.user
        self.mode = mode or self.mode
        self.session_id = new_session_id()
        self.conversation_id = new_conversation_id()
        self.started_at = datetime.now()
        self.last_active = self.started_at
        self.turn = 0

        store.start_session(self.session_id, self.user, self.mode)
        log.info("conversation session started: %s", self.session_id)
        return self.session_id

    # ------------------------------------------------------------------
    def next_turn(self) -> int:
        self.turn += 1
        self.last_active = datetime.now()
        return self.turn

    # ------------------------------------------------------------------
    def end(self, summary: str = "") -> Dict[str, Any]:
        """Close the session and return a small report."""
        if not self.session_id:
            return {}

        store.end_session(self.session_id, summary)
        report = {
            "session_id": self.session_id,
            "started_at": self.started_at.isoformat(timespec="seconds")
            if self.started_at
            else "",
            "ended_at": datetime.now().isoformat(timespec="seconds"),
            "turns": self.turn,
            "summary": summary,
        }
        log.info("conversation session ended: %s", self.session_id)
        self.session_id = ""
        self.conversation_id = ""
        self.turn = 0
        return report

    # ------------------------------------------------------------------
    def load_state(self) -> ConversationState:
        """Restore this session's persisted state."""
        state = ConversationState.from_dict(store.load_state(self.session_id))
        state.session_id = self.session_id
        state.conversation_id = self.conversation_id or state.conversation_id
        return state

    def save_state(self, state: ConversationState) -> None:
        state.touch()
        store.save_state(self.session_id, state.to_dict())

    # ------------------------------------------------------------------
    def previous_session(self) -> Optional[Dict[str, Any]]:
        return store.last_session(exclude=self.session_id)

    def resume_context(self, limit: int = 8) -> Dict[str, Any]:
        """Everything needed to continue the previous conversation."""
        previous = self.previous_session()
        if not previous:
            return {"found": False}

        previous_id = str(previous.get("session_id", ""))
        messages = store.recent_messages(previous_id, limit)
        state = ConversationState.from_dict(store.load_state(previous_id))

        return {
            "found": bool(messages or previous.get("summary")),
            "session_id": previous_id,
            "topic": previous.get("active_topic") or state.current_topic,
            "summary": previous.get("summary") or state.summary,
            "messages": messages,
            "state": state,
            "ended_at": previous.get("ended_at") or previous.get("last_active_at"),
        }

    def adopt(self, previous: Dict[str, Any], state: ConversationState) -> str:
        """Carry the previous session's topic/entities into the current one."""
        old_state: Optional[ConversationState] = previous.get("state")
        if isinstance(old_state, ConversationState):
            state.current_topic = old_state.current_topic
            state.previous_topic = old_state.previous_topic
            state.recent_entities = list(old_state.recent_entities)
            state.conversation_goal = old_state.conversation_goal
            state.summary = old_state.summary or str(previous.get("summary", ""))
        else:
            state.summary = str(previous.get("summary", ""))
            state.current_topic = str(previous.get("topic", ""))

        topic = state.current_topic
        if topic:
            return f"We were talking about {topic}."
        if state.summary:
            return f"Here's where we left off: {state.summary.splitlines()[0]}"
        return "We didn't get far last time. What would you like to pick up?"

    # ------------------------------------------------------------------
    def info(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "conversation_id": self.conversation_id,
            "mode": self.mode,
            "user": self.user,
            "turn": self.turn,
            "started_at": self.started_at.isoformat(timespec="seconds")
            if self.started_at
            else "",
            "messages": store.message_count(self.session_id)
            if self.session_id
            else 0,
        }


session_manager = SessionManager()

__all__ = [
    "SessionManager",
    "session_manager",
    "RESUME_PHRASES",
    "IDLE_TIMEOUT_MINUTES",
    "new_session_id",
]
