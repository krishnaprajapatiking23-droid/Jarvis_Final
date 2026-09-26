"""Spots negotiation positions and interests.

Signal-based text analysis: it reports patterns found in wording and what they
usually indicate. These are cues to think with, not verdicts about a person --
every result carries its own confidence and the evidence it matched on.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List

__all__ = ["NegotiationReader", "negotiation", "analyse"]

PATTERNS: Dict[str, "re.Pattern[str]"] = {
    "position": re.compile(r"\b(i want|i need|my price|non[- ]negotiable|the deal is)\b", re.IGNORECASE),
    "interest": re.compile(r"\b(because i|so that i|what matters|i care about|the reason)\b", re.IGNORECASE),
    "concession": re.compile(r"\b(i could|i'?d accept|if you|i'?m willing|meet in the middle)\b", re.IGNORECASE),
    "walkaway": re.compile(r"\b(otherwise|or i'?ll|i'?ll go elsewhere|deal breaker|final offer)\b", re.IGNORECASE),
}

GUIDANCE: Dict[str, str] = {
    "position": "A stated position; look for the interest behind it.",
    "interest": "The real lever -- negotiate here, not on positions.",
    "concession": "A trade is on offer; name what you give in return.",
    "walkaway": "Their alternative is in play; check whether it is credible.",
}


class NegotiationReader:
    """Spots negotiation positions and interests."""

    name = "negotiation"
    description = "Spots negotiation positions and interests."

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


negotiation = NegotiationReader()


def analyse(text: str) -> Dict[str, Any]:
    return negotiation.analyse(text)
