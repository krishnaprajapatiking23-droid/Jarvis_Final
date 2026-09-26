"""Detects disagreement and suggests a de-escalating move.

Signal-based text analysis: it reports patterns found in wording and what they
usually indicate. These are cues to think with, not verdicts about a person --
every result carries its own confidence and the evidence it matched on.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List

__all__ = ["ConflictReader", "conflict", "analyse"]

PATTERNS: Dict[str, "re.Pattern[str]"] = {
    "blame": re.compile(r"\b(you (?:always|never)|your fault|because of you|you broke)\b", re.IGNORECASE),
    "escalation": re.compile(r"\b(ridiculous|absurd|nonsense|stupid|terrible|worst)\b", re.IGNORECASE),
    "withdrawal": re.compile(r"\b(forget it|never mind|whatever|don'?t bother|drop it)\b", re.IGNORECASE),
    "repair": re.compile(r"\b(sorry|my fault|i was wrong|let'?s fix|fair enough)\b", re.IGNORECASE),
}

GUIDANCE: Dict[str, str] = {
    "blame": "Separate the person from the problem; restate the issue neutrally.",
    "escalation": "Lower the temperature: shorter sentences, no counter-claims.",
    "withdrawal": "Invite them back once, then respect the no.",
    "repair": "Accept the repair attempt immediately and move on.",
}


class ConflictReader:
    """Detects disagreement and suggests a de-escalating move."""

    name = "conflict"
    description = "Detects disagreement and suggests a de-escalating move."

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


conflict = ConflictReader()


def analyse(text: str) -> Dict[str, Any]:
    return conflict.analyse(text)
