"""Interprets described body language from text. Text-only: it reads descriptions, it does not see.

Signal-based text analysis: it reports patterns found in wording and what they
usually indicate. These are cues to think with, not verdicts about a person --
every result carries its own confidence and the evidence it matched on.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List

__all__ = ["BodyLanguageReader", "body_language", "analyse"]

PATTERNS: Dict[str, "re.Pattern[str]"] = {
    "closed": re.compile(r"\b(arms? crossed|turned away|stepped back|avoided eye contact|closed off)\b", re.IGNORECASE),
    "open": re.compile(r"\b(leaned in|made eye contact|smiled|nodded|open palms?|relaxed)\b", re.IGNORECASE),
    "anxious": re.compile(r"\b(fidget|tapping|shifting|bouncing (?:leg|knee)|wringing)\b", re.IGNORECASE),
    "dominant": re.compile(r"\b(stood over|loomed|pointed at|took the head|interrupted)\b", re.IGNORECASE),
}

GUIDANCE: Dict[str, str] = {
    "closed": "Disengagement or discomfort; give space before pressing.",
    "open": "Engagement; a good moment to raise the real topic.",
    "anxious": "Nervous energy; slow down and lower the stakes.",
    "dominant": "Status display; do not mirror it, stay level.",
}


class BodyLanguageReader:
    """Interprets described body language from text."""

    name = "body_language"
    description = "Interprets described body language from text."

    def signals(self, text: str) -> Dict[str, List[str]]:
        """Every pattern that matched, with the words that matched it."""
        found: Dict[str, List[str]] = {}
        for label, pattern in PATTERNS.items():
            hits = [m.group(0) for m in pattern.finditer(str(text or ""))]
            if hits:
                found[label] = hits
        return found

    def dominant(self, text: str) -> str:
        found = self.signals(text)
        if not found:
            return ""
        return max(found.items(), key=lambda item: len(item[1]))[0]

    def confidence(self, text: str) -> float:
        """Low by design: one or two keyword hits is weak evidence."""
        words = len(str(text or "").split())
        hits = sum(len(v) for v in self.signals(text).values())
        if not hits or not words:
            return 0.0
        return round(min(0.75, hits / max(6.0, words / 4.0)), 3)

    def analyse(self, text: str) -> Dict[str, Any]:
        found = self.signals(text)
        top = self.dominant(text)
        return {
            "signals": found,
            "dominant": top,
            "confidence": self.confidence(text),
            "guidance": GUIDANCE.get(top, "Not enough signal to say anything useful."),
            "caveat": "Language cues only. Ask before concluding.",
        }


body_language = BodyLanguageReader()


def analyse(text: str) -> Dict[str, Any]:
    return body_language.analyse(text)
