"""Detects the emotional need behind a message and suggests a supportive reply.

Signal-based text analysis: it reports patterns found in wording and what they
usually indicate. These are cues to think with, not verdicts about a person --
every result carries its own confidence and the evidence it matched on.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List

__all__ = ["EmpathyReader", "empathy", "analyse"]

PATTERNS: Dict[str, "re.Pattern[str]"] = {
    "distress": re.compile(r"\b(struggling|overwhelmed|exhausted|burnt out|can'?t cope|hopeless|anxious|scared|worried|stressed)\b", re.IGNORECASE),
    "frustration": re.compile(r"\b(frustrated|annoyed|fed up|sick of|again|still not working|useless)\b", re.IGNORECASE),
    "sadness": re.compile(r"\b(sad|down|lonely|miss|grief|hurt|upset)\b", re.IGNORECASE),
    "joy": re.compile(r"\b(happy|great|excited|thrilled|delighted|proud|finally)\b", re.IGNORECASE),
}

GUIDANCE: Dict[str, str] = {
    "distress": "Acknowledge the weight of it before offering any fix.",
    "frustration": "Name the frustration, own any part you caused, then act.",
    "sadness": "Stay with the feeling; do not rush to solutions.",
    "joy": "Match the energy and be specific about what went well.",
}


class EmpathyReader:
    """Detects the emotional need behind a message and suggests a supportive reply."""

    name = "empathy"
    description = "Detects the emotional need behind a message and suggests a supportive reply."

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


empathy = EmpathyReader()


def analyse(text: str) -> Dict[str, Any]:
    return empathy.analyse(text)
