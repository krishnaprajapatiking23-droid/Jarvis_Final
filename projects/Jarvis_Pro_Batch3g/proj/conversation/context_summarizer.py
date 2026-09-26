"""
==========================================
JARVIS PRO
Context Summarizer  (feature 3.20)
==========================================

Compresses older turns into a rolling summary so long conversations stay
inside the context window (3.19) without losing what matters:

    facts, decisions, active topics, unresolved questions,
    user preferences, entities and previous actions

Summarisation is extractive and deterministic by default, so it works with
no model and no network.  When an LLM callable is supplied it is used to
polish the summary, and any failure silently falls back to the extractive
result.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Callable, Dict, List, Optional

log = logging.getLogger("jarvis.conversation.summary")

# Trigger summarisation once the session exceeds this many stored messages.
SUMMARY_EVERY = 12
MAX_SUMMARY_CHARS = 1200

FACT_PATTERNS = (
    r"\bmy name is\b.*",
    r"\bi am\b.*",
    r"\bi'm\b.*",
    r"\bmy favourite\b.*",
    r"\bmy favorite\b.*",
    r"\bi like\b.*",
    r"\bi prefer\b.*",
    r"\bi live in\b.*",
    r"\bi work\b.*",
    r"\bi use\b.*",
    r"\bi don'?t like\b.*",
    r"\bmy city is\b.*",
    r"\bremember that\b.*",
)

DECISION_PATTERNS = (
    r"\blet'?s\b.*",
    r"\bwe will\b.*",
    r"\bi will\b.*",
    r"\bi decided\b.*",
    r"\bgo with\b.*",
)


class ContextSummarizer:
    """Builds and maintains the rolling conversation summary."""

    def __init__(self, llm: Optional[Callable[[str], str]] = None) -> None:
        self.llm = llm

    # ------------------------------------------------------------------
    def should_summarize(self, message_count: int, last_covered: int) -> bool:
        """True when enough new messages exist to justify a new summary."""
        return message_count - last_covered >= SUMMARY_EVERY

    # ------------------------------------------------------------------
    def extract(self, messages: List[Dict[str, Any]]) -> Dict[str, List[str]]:
        """Pull the durable parts out of a block of messages."""
        buckets: Dict[str, List[str]] = {
            "facts": [],
            "preferences": [],
            "decisions": [],
            "topics": [],
            "entities": [],
            "actions": [],
            "open_questions": [],
        }

        for message in messages:
            role = str(message.get("role", ""))
            text = str(message.get("text", "")).strip()
            if not text:
                continue
            lowered = text.lower()

            topic = str(message.get("topic", "")).strip()
            if topic and topic not in buckets["topics"]:
                buckets["topics"].append(topic)

            for entity in message.get("entities") or []:
                name = str(entity.get("name", "")).strip()
                if name and name not in buckets["entities"]:
                    buckets["entities"].append(name)

            if role == "user":
                for pattern in FACT_PATTERNS:
                    match = re.search(pattern, lowered)
                    if match:
                        snippet = match.group(0).strip().rstrip(".")
                        bucket = (
                            "preferences"
                            if any(
                                word in snippet
                                for word in ("favourite", "favorite", "like", "prefer")
                            )
                            else "facts"
                        )
                        if snippet not in buckets[bucket]:
                            buckets[bucket].append(snippet)

                for pattern in DECISION_PATTERNS:
                    match = re.search(pattern, lowered)
                    if match:
                        snippet = match.group(0).strip().rstrip(".")
                        if snippet not in buckets["decisions"]:
                            buckets["decisions"].append(snippet)

                if text.endswith("?"):
                    buckets["open_questions"].append(text)

            else:
                intent = str(message.get("intent", "")).strip()
                if intent and intent not in ("conversation", "chat"):
                    label = f"{intent}: {text[:80]}"
                    if label not in buckets["actions"]:
                        buckets["actions"].append(label)
                # A JARVIS answer closes the most recent open question.
                if buckets["open_questions"]:
                    buckets["open_questions"].pop()

        return buckets

    # ------------------------------------------------------------------
    def render(self, buckets: Dict[str, List[str]], previous: str = "") -> str:
        """Turn extracted buckets (plus any earlier summary) into text."""
        lines: List[str] = []
        if previous:
            lines.append(previous.strip())

        labels = (
            ("facts", "Facts"),
            ("preferences", "Preferences"),
            ("decisions", "Decisions"),
            ("topics", "Topics discussed"),
            ("entities", "Entities"),
            ("actions", "Actions performed"),
            ("open_questions", "Unresolved questions"),
        )
        for key, label in labels:
            values = [value for value in buckets.get(key, []) if value][:6]
            if values:
                lines.append(f"{label}: " + "; ".join(values))

        summary = "\n".join(lines).strip()
        if len(summary) > MAX_SUMMARY_CHARS:
            summary = summary[:MAX_SUMMARY_CHARS].rsplit("\n", 1)[0]
        return summary

    # ------------------------------------------------------------------
    def summarize(
        self,
        messages: List[Dict[str, Any]],
        previous: str = "",
        use_llm: bool = False,
    ) -> str:
        """Produce a summary for ``messages``, merged with ``previous``."""
        if not messages:
            return previous

        try:
            buckets = self.extract(messages)
            summary = self.render(buckets, previous)
        except Exception as error:  # pragma: no cover - defensive
            log.warning("summary extraction failed: %s", error)
            return previous

        if use_llm and self.llm and summary:
            try:
                prompt = (
                    "Rewrite the following conversation notes as a compact "
                    "summary. Keep every fact, preference, decision, entity "
                    "and unresolved question. No preamble.\n\n" + summary
                )
                polished = self.llm(prompt)
                if isinstance(polished, str) and polished.strip():
                    return polished.strip()[:MAX_SUMMARY_CHARS]
            except Exception as error:
                log.warning("llm summarisation failed, using extractive: %s", error)

        return summary


context_summarizer = ContextSummarizer()

__all__ = [
    "ContextSummarizer",
    "context_summarizer",
    "SUMMARY_EVERY",
    "MAX_SUMMARY_CHARS",
]
