"""
==========================================
JARVIS PRO
Context Ranker  (feature 3.19)
==========================================

Chooses WHICH past messages are worth sending to the model instead of
dumping the whole history.

Ranking signals
---------------
  * lexical overlap with the current message (strongest)
  * topic match
  * entity match
  * recency
  * role (the user's own words rank slightly above JARVIS replies)

When ``memory.memory_ranker`` is importable its scoring is reused for
long-term memory items so the project keeps one ranking philosophy.
"""

from __future__ import annotations

import difflib
import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence

log = logging.getLogger("jarvis.conversation.ranker")

STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "is", "are", "was", "were", "be",
    "been", "do", "does", "did", "to", "of", "in", "on", "at", "for", "with",
    "about", "it", "this", "that", "you", "i", "me", "my", "your", "what",
    "who", "how", "why", "when", "where", "can", "could", "would", "please",
    "jarvis", "tell", "so", "just", "now",
}

# Budget for the assembled context block.
MAX_RECENT_TURNS = 6
MAX_RELEVANT_MESSAGES = 4
MAX_CONTEXT_CHARS = 4000


def keywords(text: str) -> List[str]:
    """Content words of ``text``, lowercased and de-duplicated."""
    if not text:
        return []
    words = re.findall(r"[a-z0-9+#]+", text.lower())
    seen: List[str] = []
    for word in words:
        if len(word) > 2 and word not in STOPWORDS and word not in seen:
            seen.append(word)
    return seen


def _overlap(left: Sequence[str], right: Sequence[str]) -> float:
    if not left or not right:
        return 0.0
    shared = set(left) & set(right)
    return len(shared) / float(len(set(left)))


def _age_hours(timestamp: Optional[str]) -> float:
    if not timestamp:
        return 999.0
    try:
        moment = datetime.fromisoformat(str(timestamp))
    except Exception:
        return 999.0
    return max((datetime.now() - moment).total_seconds() / 3600.0, 0.0)


class ContextRanker:
    """Scores and selects context items for the model prompt."""

    # ------------------------------------------------------------------
    def score(
        self,
        message: Dict[str, Any],
        query_words: Sequence[str],
        topic: str = "",
        entity_names: Sequence[str] = (),
    ) -> float:
        text = str(message.get("text", ""))
        if not text.strip():
            return 0.0

        words = keywords(text)
        score = _overlap(query_words, words) * 60.0

        # Fuzzy similarity catches paraphrases that word overlap misses.
        if query_words:
            ratio = difflib.SequenceMatcher(
                None, " ".join(query_words), " ".join(words)
            ).ratio()
            score += ratio * 15.0

        message_topic = str(message.get("topic", "")).lower()
        if topic and message_topic and topic.lower() in message_topic:
            score += 20.0

        lowered = text.lower()
        for name in entity_names:
            if name and name.lower() in lowered:
                score += 10.0

        hours = _age_hours(message.get("created_at"))
        score += max(0.0, 12.0 - hours)

        if str(message.get("role")) == "user":
            score += 3.0

        return round(score, 2)

    # ------------------------------------------------------------------
    def rank(
        self,
        messages: List[Dict[str, Any]],
        query: str,
        topic: str = "",
        entities: Optional[List[Dict[str, Any]]] = None,
        limit: int = MAX_RELEVANT_MESSAGES,
    ) -> List[Dict[str, Any]]:
        """Return the ``limit`` most relevant messages, best first."""
        if not messages:
            return []

        query_words = keywords(query)
        names = [str(entity.get("name", "")) for entity in (entities or [])]

        scored: List[tuple[float, Dict[str, Any]]] = []
        for message in messages:
            value = self.score(message, query_words, topic, names)
            if value > 5.0:
                scored.append((value, message))

        scored.sort(key=lambda pair: pair[0], reverse=True)
        chosen: List[Dict[str, Any]] = []
        for value, message in scored[:limit]:
            item = dict(message)
            item["_score"] = value
            chosen.append(item)
        return chosen

    # ------------------------------------------------------------------
    def rank_memories(self, query: str, memories: List[Any]) -> List[Any]:
        """Rank long-term memories, reusing the project's memory ranker."""
        if not memories:
            return []
        try:  # pragma: no cover - depends on host project state
            from memory.memory_ranker import memory_ranker

            return memory_ranker.rank(query, memories)
        except Exception as error:
            log.debug("memory_ranker unavailable, using local ranking: %s", error)

        query_words = keywords(query)
        scored = []
        for item in memories:
            text = (
                item
                if isinstance(item, str)
                else str(item.get("value", item.get("text", "")))
            )
            scored.append((_overlap(query_words, keywords(text)), item))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [item for score, item in scored if score > 0]

    # ------------------------------------------------------------------
    def build_context(
        self,
        message: str,
        state_description: str = "",
        recent: Optional[List[Dict[str, Any]]] = None,
        relevant: Optional[List[Dict[str, Any]]] = None,
        summary: str = "",
        memories: Optional[List[str]] = None,
        entities: Optional[List[Dict[str, Any]]] = None,
        tone: str = "",
    ) -> str:
        """Assemble the ordered context block handed to the model.

        Order follows the required strategy: state, entities, long-term
        memory, summary, relevant older messages, recent turns, then the
        current message.
        """
        blocks: List[str] = []

        if state_description:
            blocks.append("[CONVERSATION STATE]\n" + state_description)

        if entities:
            listed = ", ".join(
                f"{entity.get('name')} ({entity.get('type')})"
                for entity in entities[:8]
            )
            blocks.append("[ENTITIES]\n" + listed)

        if memories:
            blocks.append(
                "[WHAT I KNOW ABOUT THE USER]\n"
                + "\n".join(f"- {item}" for item in memories[:6])
            )

        if summary:
            blocks.append("[EARLIER IN THIS CONVERSATION]\n" + summary)

        if relevant:
            lines = [
                f"{item.get('role', 'user')}: {item.get('text', '')}"
                for item in relevant
            ]
            blocks.append("[RELEVANT EARLIER MESSAGES]\n" + "\n".join(lines))

        if recent:
            lines = [
                f"{item.get('role', 'user')}: {item.get('text', '')}"
                for item in recent[-MAX_RECENT_TURNS * 2 :]
            ]
            blocks.append("[RECENT TURNS]\n" + "\n".join(lines))

        if tone:
            blocks.append("[TONE]\n" + tone)

        blocks.append("[CURRENT MESSAGE]\n" + message.strip())

        context = "\n\n".join(block for block in blocks if block.strip())
        if len(context) > MAX_CONTEXT_CHARS:
            # Keep the tail: state is cheap to lose, the current message is not.
            context = context[-MAX_CONTEXT_CHARS:]
        return context


context_ranker = ContextRanker()

__all__ = [
    "ContextRanker",
    "context_ranker",
    "keywords",
    "MAX_RECENT_TURNS",
    "MAX_RELEVANT_MESSAGES",
    "MAX_CONTEXT_CHARS",
]
