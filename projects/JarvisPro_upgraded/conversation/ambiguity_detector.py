"""
==========================================
JARVIS PRO
Ambiguity Detector  (feature 3.24)
==========================================

Decides whether a command is safe to execute or whether JARVIS is guessing.

    "Open it."  with Chrome, Notepad and Calculator in recent memory
    -> ambiguous, ask which one

    "Close it."  with only Notepad in recent memory
    -> not ambiguous, resolve silently

The detector is intentionally conservative for *actions* (opening, closing,
deleting, sending) and relaxed for *questions*, because guessing wrong in a
question is cheap while guessing wrong in an action is not.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from conversation.conversation_state import ConversationState
from conversation.entity_tracker import APP, OBJECT

# Actions where a wrong guess has a real consequence.
DESTRUCTIVE_ACTIONS = {
    "delete", "remove", "erase", "clear", "uninstall", "kill", "format",
    "shutdown", "restart", "send", "post", "overwrite", "drop",
}

# Actions that change the machine state but are recoverable.
ACTION_WORDS = DESTRUCTIVE_ACTIONS | {
    "open", "close", "launch", "start", "run", "stop", "play", "pause",
    "minimize", "maximize", "focus", "switch", "install", "save", "rename",
    "move", "copy", "search", "download",
}

QUESTION_STARTERS = (
    "what", "who", "when", "where", "why", "how", "which", "is", "are",
    "was", "were", "can", "could", "do", "does", "did", "tell", "explain",
)

# Actions that cannot run without their parameters.
REQUIRED_SLOTS = {
    "send": ("file", "recipient"),
    "share": ("file", "recipient"),
    "mail": ("file", "recipient"),
    "email": ("file", "recipient"),
    "forward": ("file", "recipient"),
    "upload": ("file",),
    "delete": ("file",),
    "rename": ("file",),
    "move": ("file",),
    "copy": ("file",),
}

# "the file", "that document" - a category, not a named target.
VAGUE_OBJECTS = re.compile(
    r"\b(?:the|this|that|a|an|some|my)\s+"
    r"(?:file|files|document|doc|photo|picture|image|report|thing)\b",
    re.IGNORECASE,
)

VAGUE_RECIPIENTS = re.compile(
    r"\b(?:my|a|some)\s+"
    r"(?:friend|friends|colleague|team|boss|family|someone|him|her|them)\b",
    re.IGNORECASE,
)

# "to Rahul", "to rahul@example.com"
NAMED_RECIPIENT = re.compile(r"\bto\s+(?:[A-Z][\w.-]+|[\w.+-]+@[\w.-]+)")

# "report.pdf", "notes.txt"
NAMED_FILE = re.compile(r"\b[\w-]+\.[a-z0-9]{2,5}\b", re.IGNORECASE)


def missing_slots(text: str, action: str) -> List[str]:
    """Required parameters that ``text`` does not actually supply.

    "Send the file to my friend." -> ["file", "recipient"]
    "Send report.pdf to Rahul"    -> []
    """

    needed = REQUIRED_SLOTS.get((action or "").lower())

    if not needed:
        return []

    body = text or ""
    missing: List[str] = []

    if "file" in needed:
        if not NAMED_FILE.search(body) and VAGUE_OBJECTS.search(body):
            missing.append("file")

    if "recipient" in needed:
        if not NAMED_RECIPIENT.search(body) and VAGUE_RECIPIENTS.search(body):
            missing.append("recipient")

    return missing



def _is_question(text: str) -> bool:
    lowered = text.strip().lower()
    if lowered.endswith("?"):
        return True
    first = lowered.split()[0] if lowered.split() else ""
    return first in QUESTION_STARTERS


def _action_in(text: str) -> Optional[str]:
    lowered = text.lower()
    for word in sorted(ACTION_WORDS, key=len, reverse=True):
        if re.search(rf"\b{word}\b", lowered):
            return word
    return None


class AmbiguityDetector:
    """Flags commands whose target cannot be determined confidently."""

    def check(
        self,
        text: str,
        state: ConversationState,
        resolution: Optional[Dict[str, Any]] = None,
        entities: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Return an ambiguity report for ``text``.

        Result::

            {
                "ambiguous": bool,
                "reason": "multiple_candidates" | "no_candidate" | "",
                "reference": "it",
                "action": "open",
                "options": [entity, ...],
                "destructive": bool,
            }
        """
        report: Dict[str, Any] = {
            "ambiguous": False,
            "reason": "",
            "reference": "",
            "action": "",
            "options": [],
            "destructive": False,
            "missing": [],
        }

        if not text or not text.strip():
            return report

        resolution = resolution or {}
        named = entities or []
        action = _action_in(text)
        report["action"] = action or ""
        report["destructive"] = action in DESTRUCTIVE_ACTIONS if action else False

        # Parameter validation happens *before* reference handling:
        # "Send the file to my friend." names neither the file nor the
        # recipient, so it must be clarified instead of executed.
        if action:
            missing = missing_slots(text, action)

            if missing:
                report.update(
                    ambiguous=True,
                    reason="missing_parameters",
                    missing=missing,
                )

                return report

        references: List[str] = list(resolution.get("references") or [])
        if not references:
            return report

        # An explicitly named entity in the same sentence removes the doubt:
        # "open chrome and search in it".
        if named:
            return report

        candidates: Dict[str, List[Dict[str, Any]]] = resolution.get("candidates") or {}

        for word in references:
            options = candidates.get(word) or []

            if not options:
                # Questions can still be answered from topic/summary context.
                if action and not _is_question(text):
                    report.update(
                        ambiguous=True, reason="no_candidate", reference=word
                    )
                    return report
                continue

            if not action or _is_question(text):
                continue

            actionable = [
                option
                for option in options
                if option.get("type") in (APP, OBJECT)
            ]
            if len(actionable) > 1:
                report.update(
                    ambiguous=True,
                    reason="multiple_candidates",
                    reference=word,
                    options=actionable[:4],
                )
                return report

            if report["destructive"] and len(options) > 1:
                report.update(
                    ambiguous=True,
                    reason="multiple_candidates",
                    reference=word,
                    options=options[:4],
                )
                return report

        return report


ambiguity_detector = AmbiguityDetector()

__all__ = [
    "AmbiguityDetector",
    "ambiguity_detector",
    "ACTION_WORDS",
    "DESTRUCTIVE_ACTIONS",
    "REQUIRED_SLOTS",
    "missing_slots",
]
