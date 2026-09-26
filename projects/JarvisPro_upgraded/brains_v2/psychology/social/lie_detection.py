"""Flags linguistic patterns associated with evasion -- signals, never verdicts.

Signal-based text analysis: it reports patterns found in wording and what they
usually indicate. These are cues to think with, not verdicts about a person --
every result carries its own confidence and the evidence it matched on.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List

__all__ = ["DeceptionReader", "lie_detection", "analyse"]

PATTERNS: Dict[str, "re.Pattern[str]"] = {
    "distancing": re.compile(r"\b(that (?:person|thing)|the individual|it happened|one might)\b", re.IGNORECASE),
    "over_qualifying": re.compile(r"\b(to be honest|frankly|believe me|i swear|truthfully|honestly)\b", re.IGNORECASE),
    "hedging": re.compile(r"\b(sort of|kind of|more or less|as far as i (?:know|recall)|i think)\b", re.IGNORECASE),
    "non_denial": re.compile(r"\b(why would i|that'?s absurd|i'?d never|who told you)\b", re.IGNORECASE),
}

GUIDANCE: Dict[str, str] = {
    "distancing": "Reduced first-person language; a signal only, not proof.",
    "over_qualifying": "Insisting on honesty is weakly correlated with evasion.",
    "hedging": "Creates deniability; ask a narrower question.",
    "non_denial": "Answers a different question than the one asked.",
}


class DeceptionReader:
    """Flags linguistic patterns associated with evasion -- signals, never verdicts."""

    name = "lie_detection"
    description = "Flags linguistic patterns associated with evasion -- signals, never verdicts."

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


lie_detection = DeceptionReader()


def analyse(text: str) -> Dict[str, Any]:
    return lie_detection.analyse(text)
