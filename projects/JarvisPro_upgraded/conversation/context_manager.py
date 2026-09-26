"""
==========================================
JARVIS PRO
Context Manager  (features 3.4, 3.7, 3.8, 3.19, 3.20)
==========================================

Assembles the context block that is handed to the AI model.

Layers, in priority order:

    conversation state -> entities -> long-term memory -> rolling summary
    -> relevant older messages -> recent turns -> current message

Everything is bounded.  Recent turns are capped, relevant messages are
ranked and capped, and the summary replaces older raw history once the
session grows past the summarisation threshold.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional

from conversation import store
from conversation.context_ranker import (
    MAX_RECENT_TURNS,
    context_ranker,
)
from conversation.context_summarizer import context_summarizer
from conversation.conversation_state import ConversationState
from conversation.dialogue_memory import dialogue_memory
from conversation.history_manager import history_manager

log = logging.getLogger("jarvis.conversation.context")

MAX_MEMORIES = 5


class ContextManager:
    """Retrieves, ranks and assembles conversation context."""

    def __init__(self, llm: Optional[Callable[[str], str]] = None) -> None:
        self.llm = llm
        self.summarizer = context_summarizer
        self.ranker = context_ranker

    # ------------------------------------------------------------------
    # long-term memory (3.8)
    # ------------------------------------------------------------------
    def long_term(self, message: str, limit: int = MAX_MEMORIES) -> List[str]:
        """Relevant long-term memories, using the project's memory system."""
        found: List[str] = []

        try:  # pragma: no cover - depends on host project state
            from memory.memory_search import memory_search  # type: ignore

            for item in memory_search.search(message, limit=limit) or []:
                text = (
                    item
                    if isinstance(item, str)
                    else str(item.get("value", item.get("text", "")))
                )
                if text and text not in found:
                    found.append(text)
        except Exception as error:
            log.debug("memory_search unavailable: %s", error)

        # Conversational facts learned in this or earlier sessions.
        for fact in dialogue_memory.all():
            key = str(fact.get("key", "")).replace("_", " ")
            value = str(fact.get("value", ""))
            if not value:
                continue
            line = f"{key}: {value}"
            if line not in found:
                found.append(line)

        return found[:limit]

    # ------------------------------------------------------------------
    # summarisation (3.20)
    # ------------------------------------------------------------------
    def maybe_summarize(self, session_id: str, state: ConversationState) -> str:
        """Refresh the rolling summary when enough new turns exist.

        Returns the current summary (unchanged when no work was needed), so
        the same context is never summarised twice.
        """
        if not session_id:
            return state.summary

        try:
            count = store.message_count(session_id)
            last = store.last_summary(session_id)
            covered = int(last.get("covers_to") or 0) if last else 0
            previous = str(last.get("summary") or "") if last else state.summary

            if not self.summarizer.should_summarize(count, covered):
                return previous or state.summary

            transcript = store.recent_messages(session_id, limit=max(count, 1))
            block = transcript[covered:] if covered < len(transcript) else []
            if not block:
                return previous or state.summary

            summary = self.summarizer.summarize(
                block, previous, use_llm=bool(self.llm)
            )
            if summary and summary != previous:
                store.add_summary(session_id, summary, covered, count)
                state.summary = summary
            return summary or previous
        except Exception as error:  # pragma: no cover - defensive
            log.warning("summarisation step failed: %s", error)
            return state.summary

    # ------------------------------------------------------------------
    # assembly (3.19)
    # ------------------------------------------------------------------
    def build(
        self,
        message: str,
        state: ConversationState,
        session_id: str = "",
        entities: Optional[List[Dict[str, Any]]] = None,
        tone: str = "",
        include_memory: bool = True,
    ) -> Dict[str, Any]:
        """Build the bounded context for one turn.

        Returns ``{"context": str, "recent": [...], "relevant": [...],
        "summary": str, "memories": [...]}``.
        """
        session_id = session_id or state.session_id
        recent: List[Dict[str, Any]] = []
        relevant: List[Dict[str, Any]] = []
        memories: List[str] = []
        summary = state.summary

        try:
            recent = history_manager.recent(session_id, MAX_RECENT_TURNS)
        except Exception as error:  # pragma: no cover - defensive
            log.warning("recent history unavailable: %s", error)

        try:
            summary = self.maybe_summarize(session_id, state)
        except Exception as error:  # pragma: no cover - defensive
            log.warning("summary unavailable: %s", error)

        try:
            relevant = history_manager.relevant(
                session_id,
                message,
                topic=state.current_topic,
                entities=entities or state.active_entities,
            )
        except Exception as error:  # pragma: no cover - defensive
            log.warning("relevant history unavailable: %s", error)

        if include_memory:
            try:
                memories = self.long_term(message)
            except Exception as error:  # pragma: no cover - defensive
                log.warning("long-term memory unavailable: %s", error)

        context = self.ranker.build_context(
            message=message,
            state_description=state.describe(),
            recent=recent,
            relevant=relevant,
            summary=summary,
            memories=memories,
            entities=entities or state.recent_entities,
            tone=tone,
        )

        return {
            "context": context,
            "recent": recent,
            "relevant": relevant,
            "summary": summary,
            "memories": memories,
        }


context_manager = ContextManager()

__all__ = ["ContextManager", "context_manager", "MAX_MEMORIES"]
