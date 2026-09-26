"""Estimates communication style from writing, as a preference, not a label.

Signal-based text analysis: it reports patterns found in wording and what they
usually indicate. These are cues to think with, not verdicts about a person --
every result carries its own confidence and the evidence it matched on.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List

__all__ = ["PersonalityReader", "personality_types", "analyse"]

PATTERNS: Dict[str, "re.Pattern[str]"] = {
    "analytical": re.compile(r"\b(data|precisely|specifically|measure|metric|evidence|accurate)\b", re.IGNORECASE),
    "driver": re.compile(r"\b(quickly|get to the point|bottom line|just do|no time|decide)\b", re.IGNORECASE),
    "expressive": re.compile(r"\b(amazing|love|excited|imagine|fantastic|wow)\b", re.IGNORECASE),
    "amiable": re.compile(r"\b(if that'?s ok|whenever you|no rush|happy to|whatever suits)\b", re.IGNORECASE),
}

GUIDANCE: Dict[str, str] = {
    "analytical": "Prefers detail and sources; give numbers.",
    "driver": "Prefers the answer first; lead with the conclusion.",
    "expressive": "Prefers energy and story; keep it vivid.",
    "amiable": "Prefers warmth and low pressure; avoid hard deadlines.",
}


class PersonalityReader:
    """Estimates communication style from writing, as a preference, not a label."""

    name = "personality_types"
    description = "Estimates communication style from writing, as a preference, not a label."

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


personality_types = PersonalityReader()


def analyse(text: str) -> Dict[str, Any]:
    return personality_types.analyse(text)
