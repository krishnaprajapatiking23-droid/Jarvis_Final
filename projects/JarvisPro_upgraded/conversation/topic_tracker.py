"""
==========================================
JARVIS PRO
Topic Tracker  (features 3.12, 3.13)
==========================================

Keeps track of what the conversation is about and notices when the subject
changes.

    "Tell me about Python"            -> topic: python
    "What libraries are useful?"      -> topic: python libraries  (narrowed)
    "Which one is best for AI?"       -> topic: python libraries ai
    "By the way, what's the weather?" -> topic switch, previous kept

Topics are derived from tracked entities plus a small set of domain
keywords, so no hardcoded per-subject list is needed.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List

from conversation.entity_tracker import entity_tracker

# Explicit "changing the subject" markers.
SWITCH_MARKERS = (
    "by the way",
    "btw",
    "anyway",
    "anyways",
    "on another note",
    "different question",
    "changing the subject",
    "unrelated",
    "forget that",
    "new topic",
    "one more thing",
    "let's talk about",
    "lets talk about",
    "let's discuss",
    "lets discuss",
    "now let's",
    "now lets",
    "different topic",
    "next topic",
    "something else",
    "move on",
    "switch to",
)

# "go back to", "the first topic we discussed" - return, do not switch.
RETURN_MARKERS = (
    "go back to",
    "going back to",
    "back to",
    "return to",
    "returning to",
    "as we discussed",
    "we discussed",
    "earlier topic",
    "previous topic",
    "first topic",
    "second topic",
    "last topic",
)

# Domain keywords used when no entity is present.
DOMAINS: Dict[str, tuple[str, ...]] = {
    "weather": ("weather", "temperature", "forecast", "rain", "humidity"),
    "time": ("time", "clock", "date"),
    "news": ("news", "headlines", "current affairs"),
    "music": ("music", "song", "playlist", "spotify"),
    "email": ("email", "mail", "inbox", "gmail"),
    "files": ("file", "folder", "directory", "document"),
    "reminders": ("remind", "reminder", "alarm"),
    "notes": ("note", "notes"),
    "coding": ("code", "coding", "program", "script", "bug", "function"),
    "system": ("cpu", "ram", "battery", "disk", "shutdown", "restart"),
    "health": ("health", "exercise", "diet", "sleep"),
    "finance": ("money", "stock", "price", "invest", "salary"),
}

# Words that refine an existing topic instead of replacing it.
REFINERS = (
    "library",
    "libraries",
    "framework",
    "frameworks",
    "version",
    "tutorial",
    "tutorials",
    "example",
    "examples",
    "history",
    "creator",
    "feature",
    "features",
    "alternative",
    "alternatives",
    "ai",
    "web",
    "beginner",
    "advanced",
)

STOP_TOKENS = {
    "tell", "me", "about", "what", "is", "are", "the", "a", "an", "of",
    "for", "to", "do", "you", "know", "please", "can", "could", "jarvis",
    "explain", "give", "show", "i", "want", "need", "how", "why", "who",
    "and", "or", "in", "on", "at", "with", "more", "one", "best", "which",
    "useful", "good", "let", "lets", "talk", "talking", "discuss", "learn",
    "learning", "working", "work", "help", "now", "hey", "also", "say",
    "tell", "build", "create", "make", "got", "get", "like", "some",
    "go", "goes", "went", "back", "return", "again", "topic", "topics",
    "discussion", "discussed", "first", "second", "third", "previous",
    "earlier", "last", "something", "anything", "another", "our",
}

# A bare noun phrase only becomes the topic when the sentence introduces a
# subject. Without this, "make it responsive" would look like a new topic.
TOPIC_CUES = (
    "about",
    "talk",
    "tell me",
    "discuss",
    "learn",
    "learning",
    "working on",
    "work on",
    "explain",
    "help with",
    "what is",
    "what's",
    "who is",
    "who's",
    "how to",
    "how do",
    "build",
    "create",
    "study",
    "question",
)


class TopicTracker:
    """Derives, refines and switches the active conversation topic."""

    def __init__(self) -> None:
        self.topics: List[str] = []
        self.current_topic: str = ""
        self.previous_topic: str = ""

    # ------------------------------------------------------------------
    def detect(self, text: str) -> str:
        """Best topic phrase for ``text`` on its own (no history)."""
        if not text or not text.strip():
            return ""

        lowered = text.lower().strip()

        entities = entity_tracker.extract(text)
        subjects = [
            str(entity["name"]).lower()
            for entity in entities
            if entity.get("type") in ("topic", "project", "company", "person", "app")
        ]
        if subjects:
            return subjects[0]

        for domain, words in DOMAINS.items():
            if any(re.search(rf"\b{re.escape(word)}\b", lowered) for word in words):
                return domain

        if not any(cue in lowered for cue in TOPIC_CUES):
            # Nothing announces a subject, so keep whatever topic is active.
            return ""

        tokens = [
            token
            for token in re.findall(r"[a-z0-9+#]+", lowered)
            if token not in STOP_TOKENS and len(token) > 2
        ]
        return " ".join(tokens[:3])

    # ------------------------------------------------------------------
    def is_switch(self, text: str) -> bool:
        lowered = (text or "").lower()
        return any(marker in lowered for marker in SWITCH_MARKERS)

    # ------------------------------------------------------------------
    def is_return(self, text: str) -> bool:
        """True when the user asks to go back to an earlier topic."""
        lowered = (text or "").lower()
        return any(marker in lowered for marker in RETURN_MARKERS)

    # ------------------------------------------------------------------
    def recall_topic(self, text: str) -> str:
        """Which earlier topic the user is pointing back to, or ""."""
        lowered = (text or "").lower()

        if not self.topics:
            return ""

        # A topic named outright wins: "go back to our JARVIS discussion".
        for topic in reversed(self.topics):
            words = [word for word in topic.split() if len(word) > 2]
            if words and all(word in lowered for word in words):
                return topic

        if "first topic" in lowered:
            return self.topics[0]
        if "second topic" in lowered and len(self.topics) > 1:
            return self.topics[1]

        return self.previous_topic or ""

    # ------------------------------------------------------------------
    def _refinement(self, text: str, current: str) -> str:
        """Return a narrowed topic when ``text`` refines ``current``."""
        if not current:
            return ""
        lowered = (text or "").lower()
        found = [
            word
            for word in REFINERS
            if re.search(rf"\b{re.escape(word)}\b", lowered)
        ]
        if not found:
            return ""

        parts = current.split()
        for word in found:
            if word not in parts:
                parts.append(word)
        return " ".join(parts[:5])

    # ------------------------------------------------------------------
    def _related(self, detected: str, current: str) -> bool:
        """True when ``detected`` and ``current`` share a meaningful word.

        Used to tell a refinement ("what libraries are useful?" while on
        "python") apart from a genuinely new subject ("search for python
        tutorials" while on "chrome").
        """
        if not detected or not current:
            return False
        left = {word for word in detected.split() if word not in STOP_TOKENS}
        right = {word for word in current.split() if word not in STOP_TOKENS}
        return bool(left & right)

    # ------------------------------------------------------------------
    def track(
        self,
        text: str,
        current: str = "",
        has_reference: bool = False,
    ) -> Dict[str, Any]:
        """Update the topic given the new message.

        ``current`` is the topic held by the conversation state and
        ``has_reference`` says whether the message used a pronoun, which
        implies topic continuity.

        Result::

            {"topic": "python libraries", "previous_topic": "python",
             "changed": True, "switched": False, "refined": True}
        """
        current = current or self.current_topic
        report: Dict[str, Any] = {
            "topic": current,
            "previous_topic": self.previous_topic,
            "changed": False,
            "switched": False,
            "refined": False,
            "returned": False,
        }

        if not text or not text.strip():
            return report

        switched = self.is_switch(text)
        detected = self.detect(text)
        refined = self._refinement(text, current)
        returning = self.recall_topic(text) if self.is_return(text) else ""

        if returning:
            # Going back to an earlier subject, not starting a new one.
            topic = returning
            report["returned"] = True
        elif switched and detected:
            topic = detected
        elif (
            refined
            and not switched
            and (not detected or self._related(detected, current))
        ):
            topic = refined
            report["refined"] = True
        elif has_reference and not detected:
            topic = current
        elif detected:
            topic = detected
        else:
            topic = current

        report["switched"] = switched

        if topic and topic != current:
            report["changed"] = True
            report["previous_topic"] = current
            self.previous_topic = current
            self.current_topic = topic
            if topic not in self.topics:
                self.topics.append(topic)
        else:
            self.current_topic = topic

        report["topic"] = topic
        return report

    # ------------------------------------------------------------------
    def history(self) -> List[str]:
        return list(self.topics)

    def clear(self) -> None:
        self.topics.clear()
        self.current_topic = ""
        self.previous_topic = ""


topic_tracker = TopicTracker()

__all__ = [
    "TopicTracker",
    "topic_tracker",
    "SWITCH_MARKERS",
    "DOMAINS",
    "TOPIC_CUES",
]
