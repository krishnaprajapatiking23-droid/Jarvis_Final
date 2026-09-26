"""
==========================================
JARVIS PRO
Dialogue Memory  (features 3.6, 3.8)
==========================================

Remembers facts the user states during a conversation and answers direct
questions about them.

    "My favorite programming language is Python."
    ...
    "What programming language do I like?"
    -> "Your favorite programming language is Python."

This is a thin, well-defined layer ON TOP of the project's existing memory
system - it does not create a competing store.  Facts are written through
``memory.memory.remember`` / ``brains_v2.memory.database`` when available and
fall back to the conversation database only if those are unreachable.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger("jarvis.conversation.dialogue_memory")

# (regex, memory key, phrasing used when answering)
FACT_RULES: Tuple[Tuple[str, str, str], ...] = (
    (
        r"\bmy (?:favourite|favorite) (?P<subject>[a-z ]+?) is (?P<value>.+)$",
        "favourite_{subject}",
        "Your favourite {subject} is {value}.",
    ),
    (
        r"\bi (?:really )?(?:like|love|prefer) (?P<value>.+)$",
        "likes",
        "You like {value}.",
    ),
    (
        r"\bi (?:don't|do not|dont) like (?P<value>.+)$",
        "dislikes",
        "You don't like {value}.",
    ),
    (
        r"\bmy name is (?P<value>.+)$",
        "name",
        "Your name is {value}.",
    ),
    (
        r"\bi (?:live in|am from|'m from) (?P<value>.+)$",
        "location",
        "You live in {value}.",
    ),
    (
        r"\bmy city is (?P<value>.+)$",
        "location",
        "You live in {value}.",
    ),
    (
        r"\bi (?:work|am working|'m working) (?:at|on|for) (?P<value>.+)$",
        "work",
        "You work on {value}.",
    ),
    (
        r"\bi am (?:learning|studying) (?P<value>.+)$",
        "learning",
        "You are learning {value}.",
    ),
    (
        r"\bi'?m (?:learning|studying) (?P<value>.+)$",
        "learning",
        "You are learning {value}.",
    ),
    (
        r"\bi use (?P<value>.+)$",
        "tools",
        "You use {value}.",
    ),
    (
        r"\bmy (?P<subject>[a-z ]+?) (?:is called|is named) (?P<value>.+)$",
        "{subject}_name",
        "Your {subject} is called {value}.",
    ),
    (
        r"\bmy (?P<subject>[a-z ]+?) "
        r"(?:uses|use|is using|is built with|is written in) (?P<value>.+)$",
        "{subject}_uses",
        "Your {subject} uses {value}.",
    ),
    (
        r"\bmy (?P<subject>[a-z ]+?) is (?P<value>.+)$",
        "{subject}",
        "Your {subject} is {value}.",
    ),
    (
        r"\bremember that (?P<value>.+)$",
        "note",
        "You told me: {value}.",
    ),
)

# Questions that ask a stored fact back.
QUESTION_RULES: Tuple[Tuple[str, str], ...] = (
    (
        r"what (?:is|'s) my (?:favourite|favorite) (?P<subject>[a-z ]+?)\s*\??$",
        "favourite_{subject}",
    ),
    (
        r"what (?P<subject>[a-z ]+?) do i (?:like|prefer)\s*\??$",
        "favourite_{subject}",
    ),
    (r"what do i like\s*\??$", "likes"),
    (r"what (?:is|'s) my name\s*\??$", "name"),
    (r"who am i\s*\??$", "name"),
    (r"where do i live\s*\??$", "location"),
    (r"what (?:is|'s) my city\s*\??$", "location"),
    (r"what am i learning\s*\??$", "learning"),
    (r"what do i (?:work on|do)\s*\??$", "work"),
    (r"what do i use\s*\??$", "tools"),
    (
        r"what (?:is|'s) my (?P<subject>[a-z ]+?) called\s*\??$",
        "{subject}_name",
    ),
    (
        r"what (?:is|'s) the name of my (?P<subject>[a-z ]+?)\s*\??$",
        "{subject}_name",
    ),
    (
        r"what (?:language |framework |tool )?does my "
        r"(?P<subject>[a-z ]+?) use\s*\??$",
        "{subject}_uses",
    ),
    (
        r"what (?:is|'s) my (?P<subject>[a-z ]+?)\s*\??$",
        "{subject}",
    ),
)

STRIP_WORDS = ("programming", "favourite", "favorite")


def _normalise_subject(subject: str) -> str:
    """'programming language' and 'language' must resolve to one key."""
    words = [
        word
        for word in re.split(r"\s+", subject.strip().lower())
        if word and word not in STRIP_WORDS
    ]
    return "_".join(words) if words else "thing"


class DialogueMemory:
    """Extracts, stores and recalls conversational facts."""

    def __init__(self) -> None:
        # Local cache; the durable copy lives in the project memory system.
        self.facts: Dict[str, Dict[str, str]] = {}

    # ------------------------------------------------------------------
    # extraction
    # ------------------------------------------------------------------
    def extract(self, text: str) -> Optional[Dict[str, str]]:
        """Detect a statable fact in ``text``."""
        if not text or not text.strip():
            return None

        raw = text.strip().rstrip(".!")
        lowered = raw.lower()

        for pattern, key_template, phrasing in FACT_RULES:
            match = re.search(pattern, lowered)
            if not match:
                continue

            # Match on the lowercase copy, read from the original so the
            # stored value keeps the user's capitalisation ("Python").
            start, end = match.span("value")
            value = raw[start:end].strip(" .")
            if not value or len(value) > 120:
                continue

            subject = ""
            if "subject" in match.groupdict() and match.group("subject"):
                first, last = match.span("subject")
                subject = raw[first:last].strip()

            # Mirror the user's spelling of favourite/favorite.
            if "favorite" in lowered:
                phrasing = phrasing.replace("favourite", "favorite")

            key = key_template.format(subject=_normalise_subject(subject))
            return {
                "key": key,
                "value": value,
                "subject": subject,
                "phrasing": phrasing,
                "source": text.strip(),
            }
        return None

    # ------------------------------------------------------------------
    # storage
    # ------------------------------------------------------------------
    def remember(self, fact: Dict[str, str]) -> bool:
        """Store ``fact`` in the local cache and the project memory system."""
        key = fact.get("key", "")
        if not key:
            return False

        self.facts[key] = {
            "value": fact.get("value", ""),
            "subject": fact.get("subject", ""),
            "phrasing": fact.get("phrasing", "You told me: {value}."),
        }

        stored = False
        try:  # pragma: no cover - depends on host project state
            from memory.memory import remember as remember_fact  # type: ignore

            remember_fact(key, fact.get("value", ""))
            stored = True
        except Exception as error:
            log.debug("memory.memory unavailable: %s", error)

        if not stored:
            try:  # pragma: no cover - depends on host project state
                from brains_v2.memory.database import database  # type: ignore

                database.save("conversation_fact", key, fact.get("value", ""))
                stored = True
            except Exception as error:
                log.debug("brains_v2 memory database unavailable: %s", error)

        return stored

    # ------------------------------------------------------------------
    def learn(self, text: str) -> Optional[Dict[str, str]]:
        """Extract and store in one step. Returns the fact or None."""
        fact = self.extract(text)
        if not fact:
            return None
        self.remember(fact)
        return fact

    # ------------------------------------------------------------------
    # recall
    # ------------------------------------------------------------------
    def question_key(self, text: str) -> str:
        """Memory key a question is asking about, or ""."""
        if not text:
            return ""
        lowered = text.strip().lower()
        for pattern, key_template in QUESTION_RULES:
            match = re.search(pattern, lowered)
            if match:
                subject = match.groupdict().get("subject") or ""
                return key_template.format(subject=_normalise_subject(subject))
        return ""

    def lookup(self, key: str) -> str:
        """Fetch a stored value from cache, then the project memory system."""
        if not key:
            return ""

        record = self.facts.get(key)
        if record and record.get("value"):
            return str(record["value"])

        try:  # pragma: no cover - depends on host project state
            from memory.memory import recall  # type: ignore

            value = recall(key)
            if value:
                return str(value)
        except Exception as error:
            log.debug("memory recall unavailable: %s", error)

        try:  # pragma: no cover - depends on host project state
            from brains_v2.memory.database import database  # type: ignore

            value = database.get(key)
            if value:
                return str(value)
        except Exception as error:
            log.debug("brains_v2 memory lookup unavailable: %s", error)

        return ""

    def answer(self, text: str) -> str:
        """Answer a fact question from memory, or "" when unknown."""
        key = self.question_key(text)
        if not key:
            return ""

        value = self.lookup(key)
        if not value:
            return ""

        record = self.facts.get(key, {})
        phrasing = record.get("phrasing") or ""
        subject = record.get("subject") or key.replace("favourite_", "").replace(
            "_", " "
        )

        if phrasing:
            try:
                return phrasing.format(subject=subject, value=value)
            except Exception:
                pass

        if key.startswith("favourite_"):
            return f"Your favourite {subject} is {value}."
        if key == "name":
            return f"Your name is {value}."
        if key == "location":
            return f"You live in {value}."
        return f"You told me: {value}."

    # ------------------------------------------------------------------
    def correct(self, key: str, value: str) -> None:
        """Replace a stored fact after a user correction (3.23)."""
        record = self.facts.get(key, {})
        self.remember(
            {
                "key": key,
                "value": value,
                "subject": record.get("subject", ""),
                "phrasing": record.get("phrasing", ""),
            }
        )

    def last_fact_key(self) -> str:
        return next(reversed(self.facts), "") if self.facts else ""

    def all(self) -> List[Dict[str, Any]]:
        return [{"key": key, **value} for key, value in self.facts.items()]

    def clear(self) -> None:
        self.facts.clear()


dialogue_memory = DialogueMemory()

__all__ = ["DialogueMemory", "dialogue_memory", "FACT_RULES", "QUESTION_RULES"]
