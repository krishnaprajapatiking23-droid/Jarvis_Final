"""Detects influence tactics so they can be recognised, not deployed blindly.

Signal-based text analysis: it reports patterns found in wording and what they
usually indicate. These are cues to think with, not verdicts about a person --
every result carries its own confidence and the evidence it matched on.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List

__all__ = ["InfluenceReader", "influence", "analyse"]

PATTERNS: Dict[str, "re.Pattern[str]"] = {
    "reciprocity": re.compile(r"\b(i (?:helped|did) you|after all i|you owe|in return)\b", re.IGNORECASE),
    "commitment": re.compile(r"\b(you (?:said|agreed|promised)|as we discussed|you committed)\b", re.IGNORECASE),
    "liking": re.compile(r"\b(we'?re alike|just like you|i'?m a fan|you and i)\b", re.IGNORECASE),
    "pressure": re.compile(r"\b(right now|immediately|no time|must decide|before it'?s too late)\b", re.IGNORECASE),
}

GUIDANCE: Dict[str, str] = {
    "reciprocity": "Fine when the favour was genuine; manipulative when invoked as debt.",
    "commitment": "Check the commitment was actually made before relying on it.",
    "liking": "Pleasant, but not a reason to agree.",
    "pressure": "Time pressure is the most common manipulation signal -- slow down.",
}


class InfluenceReader:
    """Detects influence tactics so they can be recognised, not deployed blindly."""

    name = "influence"
    description = "Detects influence tactics so they can be recognised, not deployed blindly."

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


influence = InfluenceReader()


def analyse(text: str) -> Dict[str, Any]:
    return influence.analyse(text)
