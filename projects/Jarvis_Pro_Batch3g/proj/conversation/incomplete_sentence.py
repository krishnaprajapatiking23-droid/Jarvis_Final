"""
==========================================
JARVIS PRO
Incomplete Sentence Detector  (feature 3.11)
==========================================

Stops JARVIS from acting on half a sentence.

    "Open the..."            -> "Open what?"
    "Can you..."             -> "Yes, what would you like me to do?"
    "Open Chrome and..."     -> opens nothing until the rest arrives

The detector reports WHY the sentence is incomplete so the dialogue
manager can ask the right short question.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Set

# Verbs that require an object.
ACTION_WORDS: Set[str] = {
    "open", "close", "launch", "start", "run", "stop", "kill", "restart",
    "play", "pause", "search", "find", "create", "make", "delete", "remove",
    "send", "write", "read", "show", "tell", "explain", "call", "remind",
    "set", "add", "save", "download", "install", "rename", "move", "copy",
}

# Phrases that cannot end a sentence.
DANGLING_WORDS: Set[str] = {
    "and", "or", "but", "so", "then", "because", "the", "a", "an", "my",
    "your", "to", "for", "with", "about", "of", "in", "on", "at", "that",
    "if", "when", "while", "also", "plus",
}

# Openers that are polite lead-ins with nothing behind them.
LEAD_INS = (
    "can you",
    "could you",
    "would you",
    "will you",
    "please",
    "i want you to",
    "i need you to",
    "do me a favour",
    "do me a favor",
    "jarvis",
)

# Modals that leave a sentence hanging: "an assistant that can...".
MODAL_WORDS: Set[str] = {
    "can", "could", "should", "would", "will", "might", "must", "may",
    "does", "do", "is", "are", "has", "have", "needs", "wants",
}

ELLIPSIS = re.compile(r"(\.{2,}|\u2026)\s*$")


class IncompleteSentenceDetector:
    """Detects unfinished user input."""

    def analyze(self, text: str) -> Dict[str, Any]:
        """Analyse ``text``.

        Result::

            {"incomplete": True, "reason": "missing_object",
             "question": "Open what?", "verb": "open"}
        """
        report: Dict[str, Any] = {
            "incomplete": False,
            "reason": "",
            "question": "",
            "verb": "",
        }

        raw = (text or "").strip()
        if not raw:
            report.update(
                incomplete=True,
                reason="empty_input",
                question="I didn't catch that. What would you like me to do?",
            )
            return report

        has_ellipsis = bool(ELLIPSIS.search(raw))
        cleaned = ELLIPSIS.sub("", raw).strip().rstrip(",")
        lowered = cleaned.lower().rstrip(".!?")
        words = lowered.split()

        if not words:
            report.update(
                incomplete=True,
                reason="empty_input",
                question="I didn't catch that. What would you like me to do?",
            )
            return report

        # A trailing conjunction/article always means more was coming.
        if words[-1] in DANGLING_WORDS:
            verb = next((word for word in words if word in ACTION_WORDS), "")
            report.update(
                incomplete=True,
                reason="unfinished_phrase",
                verb=verb,
                question=self._question(verb, words),
            )
            return report

        # Bare lead-in with no request behind it.
        if lowered in LEAD_INS or (
            len(words) <= 3 and any(lowered == phrase for phrase in LEAD_INS)
        ):
            report.update(
                incomplete=True,
                reason="lead_in_only",
                question="Yes, what would you like me to do?",
            )
            return report

        # An action verb with nothing to act on.
        if words[0] in ACTION_WORDS:
            remainder = [
                word
                for word in words[1:]
                if word not in DANGLING_WORDS and word not in ("it", "this", "that")
            ]
            references = [word for word in words[1:] if word in ("it", "this", "that")]
            if not remainder and not references:
                report.update(
                    incomplete=True,
                    reason="missing_object",
                    verb=words[0],
                    question=self._question(words[0], words),
                )
                return report

        # Explicit ellipsis: the user trailed off, however long the
        # fragment is.  "I want to create an AI assistant that can..."
        # must ask for the rest instead of inventing the requirements.
        if has_ellipsis:
            verb = next((word for word in words if word in ACTION_WORDS), "")
            question = self._question(verb, words)
            if words[-1] in MODAL_WORDS:
                question = "Go ahead - what should it be able to do?"
            report.update(
                incomplete=True,
                reason="trailing_ellipsis",
                verb=verb,
                question=question,
            )
            return report

        return report

    # ------------------------------------------------------------------
    def _question(self, verb: str, words: list[str]) -> str:
        if verb:
            return f"{verb.capitalize()} what?"
        if words and words[0] in ("can", "could", "would", "will"):
            return "Yes, what would you like me to do?"
        return "Go on - what would you like me to do?"


incomplete_sentence = IncompleteSentenceDetector()

__all__ = [
    "IncompleteSentenceDetector",
    "incomplete_sentence",
    "ACTION_WORDS",
    "DANGLING_WORDS",
]
