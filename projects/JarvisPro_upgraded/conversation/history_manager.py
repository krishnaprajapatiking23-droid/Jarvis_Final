"""
==========================================
JARVIS PRO
History Manager  (features 3.4, 3.7, 3.8)
==========================================

Stores conversation turns and retrieves ONLY the relevant ones.

The whole database is never handed to the model.  Retrieval is layered:

    current turn  ->  recent turns  ->  relevant older messages
                  ->  rolling summary  ->  long-term memory

The in-process cache keeps the recent window hot so a normal turn costs a
single write instead of several reads.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from conversation import store
from conversation.context_ranker import context_ranker, keywords

log = logging.getLogger("jarvis.conversation.history")

RECENT_WINDOW = 12


class HistoryManager:
    """Conversation history persistence and intelligent retrieval."""

    def __init__(self) -> None:
        # session_id -> recent messages (oldest first)
        self._cache: Dict[str, List[Dict[str, Any]]] = {}

    # ------------------------------------------------------------------
    def add(
        self,
        session_id: str,
        role: str,
        text: str,
        conversation_id: str = "",
        turn: int = 0,
        intent: str = "",
        topic: str = "",
        emotion: str = "",
        entities: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        """Persist one turn and update the hot cache."""
        if not session_id or not (text or "").strip():
            return

        record = {
            "session_id": session_id,
            "conversation_id": conversation_id,
            "turn": turn,
            "role": role,
            "text": text,
            "intent": intent,
            "topic": topic,
            "emotion": emotion,
            "entities": entities or [],
            "created_at": store._now(),
        }

        window = self._cache.setdefault(session_id, [])
        window.append(record)
        del window[:-RECENT_WINDOW]

        store.add_message(
            session_id=session_id,
            role=role,
            text=text,
            conversation_id=conversation_id,
            turn=turn,
            intent=intent,
            topic=topic,
            emotion=emotion,
            entities=entities or [],
        )

    # ------------------------------------------------------------------
    def recent(self, session_id: str, limit: int = 6) -> List[Dict[str, Any]]:
        """Most recent turns, oldest first. Served from cache when possible."""
        if not session_id:
            return []

        window = self._cache.get(session_id)
        if window is None:
            window = store.recent_messages(session_id, RECENT_WINDOW)
            self._cache[session_id] = window
        return window[-limit:]

    # ------------------------------------------------------------------
    def relevant(
        self,
        session_id: str,
        query: str,
        topic: str = "",
        entities: Optional[List[Dict[str, Any]]] = None,
        limit: int = 4,
        include_previous_sessions: bool = False,
    ) -> List[Dict[str, Any]]:
        """Older messages worth re-reading for ``query``.

        Recent turns are excluded because they are already included
        verbatim; this looks further back for the genuinely relevant bits.
        """
        terms = keywords(query)
        for entity in entities or []:
            name = str(entity.get("name", "")).strip().lower()
            if name:
                terms.append(name)
        if topic:
            terms.extend(keywords(topic))

        if not terms:
            return []

        try:
            candidates = store.search_messages(
                terms,
                limit=40,
                session_id=None if include_previous_sessions else session_id,
            )
        except Exception as error:  # pragma: no cover - defensive
            log.warning("history search failed: %s", error)
            return []

        recent_texts = {
            str(item.get("text", "")) for item in self.recent(session_id, RECENT_WINDOW)
        }
        candidates = [
            item for item in candidates if str(item.get("text", "")) not in recent_texts
        ]

        return context_ranker.rank(candidates, query, topic, entities, limit)

    # ------------------------------------------------------------------
    def repeated_question(self, session_id: str, text: str) -> bool:
        """True when the user just asked something very similar (3.26)."""
        target = " ".join(keywords(text))
        if not target:
            return False

        for message in self.recent(session_id, 6):
            if message.get("role") != "user":
                continue
            if str(message.get("text", "")).strip().lower() == text.strip().lower():
                return True
            other = " ".join(keywords(str(message.get("text", ""))))
            if not other or not target:
                continue
            shared = set(target.split()) & set(other.split())
            if len(shared) >= max(2, int(len(set(target.split())) * 0.8)):
                return True
        return False

    # ------------------------------------------------------------------
    def transcript(self, session_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        return store.recent_messages(session_id, limit)

    def count(self, session_id: str) -> int:
        return store.message_count(session_id)

    def clear_cache(self, session_id: str = "") -> None:
        if session_id:
            self._cache.pop(session_id, None)
        else:
            self._cache.clear()


history_manager = HistoryManager()

__all__ = ["HistoryManager", "history_manager", "RECENT_WINDOW"]
