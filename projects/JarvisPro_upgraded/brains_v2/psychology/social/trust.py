"""Scores how trust-building or trust-eroding a message is.

Signal-based text analysis: it reports patterns found in wording and what they
usually indicate. These are cues to think with, not verdicts about a person --
every result carries its own confidence and the evidence it matched on.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List

__all__ = ["TrustReader", "trust", "analyse"]

PATTERNS: Dict[str, "re.Pattern[str]"] = {
    "transparency": re.compile(r"\b(here'?s why|to be clear|i don'?t know|i was wrong|the catch is)\b", re.IGNORECASE),
    "reliability": re.compile(r"\b(as promised|on time|i'?ll confirm|done|delivered)\b", re.IGNORECASE),
    "vagueness": re.compile(r"\b(soon|somehow|we'?ll see|probably fine|trust me|don'?t worry)\b", re.IGNORECASE),
    "overclaim": re.compile(r"\b(guaranteed|100%|never fails|perfect|flawless|risk[- ]free)\b", re.IGNORECASE),
}

GUIDANCE: Dict[str, str] = {
    "transparency": "Raises trust: admitting limits is the strongest signal.",
    "reliability": "Raises trust: concrete, checkable claims.",
    "vagueness": "Lowers trust: replace with a specific commitment.",
    "overclaim": "Lowers trust sharply: absolute claims invite disproof.",
}


class TrustReader:
    """Scores how trust-building or trust-eroding a message is."""

    name = "trust"
    description = "Scores how trust-building or trust-eroding a message is."

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


trust = TrustReader()


def analyse(text: str) -> Dict[str, Any]:
    return trust.analyse(text)
