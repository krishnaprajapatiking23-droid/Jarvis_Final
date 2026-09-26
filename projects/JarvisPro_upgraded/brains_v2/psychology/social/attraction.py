"""Reads rapport and warmth signals in a conversation.

Signal-based text analysis: it reports patterns found in wording and what they
usually indicate. These are cues to think with, not verdicts about a person --
every result carries its own confidence and the evidence it matched on.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List

__all__ = ["RapportReader", "attraction", "analyse"]

PATTERNS: Dict[str, "re.Pattern[str]"] = {
    "warmth": re.compile(r"\b(thanks|appreciate|glad|lovely|nice to|good to hear)\b", re.IGNORECASE),
    "reciprocation": re.compile(r"\b(me too|same here|i agree|exactly|likewise)\b", re.IGNORECASE),
    "distance": re.compile(r"\b(anyway|as i said|moving on|regardless|whatever you think)\b", re.IGNORECASE),
    "interest": re.compile(r"\b(tell me more|what do you think|how did you|go on)\b", re.IGNORECASE),
}

GUIDANCE: Dict[str, str] = {
    "warmth": "Rapport is building; keep the register.",
    "reciprocation": "Shared ground; name it explicitly.",
    "distance": "Rapport is cooling; check whether something landed badly.",
    "interest": "Genuine curiosity; answer generously.",
}


class RapportReader:
    """Reads rapport and warmth signals in a conversation."""

    name = "attraction"
    description = "Reads rapport and warmth signals in a conversation."

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


attraction = RapportReader()


def analyse(text: str) -> Dict[str, Any]:
    return attraction.analyse(text)
