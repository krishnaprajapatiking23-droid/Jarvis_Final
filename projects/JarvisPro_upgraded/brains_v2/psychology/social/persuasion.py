"""Identifies persuasive structure in a message.

Signal-based text analysis: it reports patterns found in wording and what they
usually indicate. These are cues to think with, not verdicts about a person --
every result carries its own confidence and the evidence it matched on.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List

__all__ = ["PersuasionReader", "persuasion", "analyse"]

PATTERNS: Dict[str, "re.Pattern[str]"] = {
    "evidence": re.compile(r"\b(because|data|study|evidence|shows that|measured|benchmark)\b", re.IGNORECASE),
    "social_proof": re.compile(r"\b(everyone|most people|others are|popular|widely used)\b", re.IGNORECASE),
    "scarcity": re.compile(r"\b(only|limited|last chance|running out|deadline|hurry)\b", re.IGNORECASE),
    "authority": re.compile(r"\b(expert|official|according to|research|documented)\b", re.IGNORECASE),
}

GUIDANCE: Dict[str, str] = {
    "evidence": "Strongest form: keep it and cite the source.",
    "social_proof": "Weak on its own; pair it with evidence.",
    "scarcity": "Use sparingly and only when the deadline is real.",
    "authority": "Name the authority so it can be checked.",
}


class PersuasionReader:
    """Identifies persuasive structure in a message."""

    name = "persuasion"
    description = "Identifies persuasive structure in a message."

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


persuasion = PersuasionReader()


def analyse(text: str) -> Dict[str, Any]:
    return persuasion.analyse(text)
