"""
==========================================
JARVIS PRO
Correction Handler  (feature 3.23)
==========================================

Understands when the user is fixing something they just said.

    "Open Chrome."            -> Chrome opens
    "No, I meant Edge."       -> "Got it. Opening Microsoft Edge instead."

    "My favourite language is Java."
    "Actually, I meant Python."   -> the stored fact is replaced

This complements ``brains_v2.correction`` which fixes speech-recognition
typos.  That module stays responsible for "chrme" -> "chrome"; this one is
responsible for intent-level corrections.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from conversation.conversation_state import ConversationState
from conversation.entity_tracker import entity_tracker
from conversation.incomplete_sentence import ACTION_WORDS

# Patterns that introduce a correction, ordered strongest first.
CORRECTION_PATTERNS: tuple[str, ...] = (
    r"^correction[,:\s]+(?P<value>.+)$",
    r"^my mistake[,:\s]+(?P<value>.+)$",
    r"^no[,\s]+i\s+meant\s+(?P<value>.+)$",
    r"^no[,\s]+(?P<value>.+)\s+instead$",
    r"^actually[,\s]+i\s+meant\s+(?P<value>.+)$",
    r"^actually[,\s]+(?:it'?s|its|it is|make it|use)\s+(?P<value>.+)$",
    r"^i\s+meant\s+(?P<value>.+)$",
    r"^sorry[,\s]+i\s+meant\s+(?P<value>.+)$",
    r"^not\s+.+?[,\s]+(?P<value>.+)$",
    r"^no[,\s]+(?P<value>.+)$",
    r"^actually[,\s]+(?P<value>.+)$",
    r"^change\s+(?:that|it)\s+to\s+(?P<value>.+)$",
    r"^make\s+(?:that|it)\s+(?P<value>.+)$",
    r"^rather\s+(?P<value>.+)$",
    r"^instead\s+(?P<value>.+)$",
)

# Verb -> gerund, used for natural correction acknowledgements.
GERUNDS = {
    "open": "Opening",
    "close": "Closing",
    "launch": "Launching",
    "start": "Starting",
    "stop": "Stopping",
    "run": "Running",
    "play": "Playing",
    "pause": "Pausing",
    "search": "Searching for",
    "find": "Looking for",
    "send": "Sending",
    "create": "Creating",
    "make": "Making",
    "delete": "Deleting",
    "remove": "Removing",
    "install": "Installing",
    "download": "Downloading",
    "save": "Saving",
    "remind": "Setting a reminder for",
}

# Marker words that must not survive inside the corrected value itself:
# "correction: my project uses Python" -> "my project uses Python".
MARKER_PREFIX = re.compile(
    r"^(?:correction|actually|sorry|no|not|i\s+mean|i\s+meant|my\s+mistake)"
    r"\b[\s,:;-]*",
    re.IGNORECASE,
)

MARKERS = (
    "i meant",
    "no, i meant",
    "actually",
    "instead",
    "not that",
    "change that to",
    "make that",
    "correction",
    "my mistake",
)


class CorrectionHandler:
    """Detects corrections and rewrites the previous request."""

    # ------------------------------------------------------------------
    def detect(self, text: str, state: ConversationState) -> Dict[str, Any]:
        """Detect a correction in ``text``.

        Result::

            {
                "is_correction": bool,
                "value": "Edge",              # the corrected value
                "pattern": "^no, i meant...",
                "target": "action" | "fact" | "detail",
                "command": "open Edge",       # rebuilt request when possible
                "replaced": "Chrome",
            }
        """
        report: Dict[str, Any] = {
            "is_correction": False,
            # same flag under the shorter name some callers use
            "corrected": False,
            "value": "",
            "pattern": "",
            "target": "",
            "command": "",
            "replaced": "",
            "verb": "",
        }

        if not text or not text.strip():
            return report

        cleaned = text.strip().rstrip(".!").strip()
        lowered = cleaned.lower()

        # A bare "no" is a refusal, not a correction.
        if lowered in {"no", "nope", "nah"}:
            return report

        if not any(marker in lowered for marker in MARKERS) and not lowered.startswith(
            ("no ", "no,", "not ")
        ):
            return report

        value = ""
        matched = ""
        for pattern in CORRECTION_PATTERNS:
            match = re.match(pattern, lowered)
            if match:
                value = (match.group("value") or "").strip()
                matched = pattern
                break

        # Strip any marker words the pattern left in front of the value.
        for _ in range(2):
            stripped = MARKER_PREFIX.sub("", value).strip()
            if stripped == value:
                break
            value = stripped

        if not value:
            return report

        report.update(is_correction=True, value=value, pattern=matched)
        # the same flag under the shorter name some callers use
        report["corrected"] = True
        report["target"] = self._classify(state)
        rebuilt = self._rebuild(value, state)
        report["command"] = rebuilt.get("command", "")
        report["replaced"] = rebuilt.get("replaced", "")
        report["verb"] = rebuilt.get("verb", "")
        return report

    # ------------------------------------------------------------------
    def _classify(self, state: ConversationState) -> str:
        action = (state.last_jarvis_action or "").lower()
        intent = (state.last_user_intent or "").lower()
        if action and action not in ("chat", "conversation", ""):
            return "action"
        if intent in ("memory", "knowledge"):
            return "fact"
        return "detail"

    # ------------------------------------------------------------------
    def _rebuild(self, value: str, state: ConversationState) -> Dict[str, str]:
        """Rewrite the previous message with the corrected value."""
        previous = (state.last_user_message or "").strip()
        if not previous:
            return {"command": value, "replaced": ""}

        new_entities = entity_tracker.extract(value)
        old_entities = entity_tracker.extract(previous)

        # Replace an entity of the same type when we can (Chrome -> Edge,
        # tomorrow -> today).
        if new_entities and old_entities:
            replacement = new_entities[0]
            for candidate in old_entities:
                if candidate.get("type") == replacement.get("type"):
                    command = re.sub(
                        rf"\b{re.escape(str(candidate['text']))}\b",
                        str(replacement["name"]),
                        previous,
                        count=1,
                        flags=re.IGNORECASE,
                    )
                    return {
                        "command": command,
                        "replaced": str(candidate["name"]),
                    }

        # Time-only corrections: "No, I meant today."
        time_words = (
            "today",
            "tomorrow",
            "yesterday",
            "tonight",
            "morning",
            "afternoon",
            "evening",
            "next week",
            "last week",
        )
        lowered_value = value.lower()
        for word in time_words:
            if word not in lowered_value:
                continue
            for other in time_words:
                if other != word and re.search(rf"\b{other}\b", previous.lower()):
                    command = re.sub(
                        rf"\b{other}\b",
                        word,
                        previous,
                        count=1,
                        flags=re.IGNORECASE,
                    )
                    return {"command": command, "replaced": other}
            return {"command": f"{previous} {word}", "replaced": ""}

        # Preserve the action verb: "open chrome" + "edge" -> "open edge".
        parts = previous.split()
        bare = [word.lower().strip(".,!?") for word in parts]
        for index, word in enumerate(bare):
            if word in ACTION_WORDS:
                return {
                    "command": " ".join(parts[: index + 1] + [value]),
                    "replaced": " ".join(parts[index + 1 :]),
                    "verb": word,
                }

        # Otherwise replace the object of the previous request.
        if len(parts) >= 2:
            command = " ".join(parts[:1] + [value])
            return {"command": command, "replaced": " ".join(parts[1:])}

        return {"command": value, "replaced": ""}

    # ------------------------------------------------------------------
    def acknowledge(self, report: Dict[str, Any]) -> str:
        """Short, natural acknowledgement of a correction."""
        value = str(report.get("value", "")).strip()
        if not value:
            return "Got it, corrected."

        entities = entity_tracker.extract(value)
        if entities:
            display = str(entities[0]["name"])
        else:
            words = value.split()
            if len(words) > 3:
                # A whole new instruction: echoing it back sounds robotic,
                # the reply itself already says what is being done.
                return "Got it, corrected."
            display = value[0].upper() + value[1:]

        verb = str(report.get("verb", "")).lower()
        gerund = GERUNDS.get(verb, "")
        if report.get("target") == "action" and gerund:
            return f"Got it. {gerund} {display} instead."
        if report.get("target") == "action":
            return f"Got it - {display} instead."
        return f"Got it - {display} it is."


correction_handler = CorrectionHandler()

__all__ = ["CorrectionHandler", "correction_handler", "CORRECTION_PATTERNS"]
