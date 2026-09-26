"""Confidence scoring for answers and decisions (roadmap sections 1 and 19).

Produces a 0..1 score from signals that are actually available offline:
evidence count, source agreement, whether a model was used, hedging language
and answer length. Deliberately conservative -- unknown means low.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Optional, Sequence

__all__ = ["ConfidenceScorer", "confidence", "score"]

_HEDGES = re.compile(
    r"\b(maybe|perhaps|possibly|probably|might|could be|i think|i believe|"
    r"not sure|unsure|roughly|approximately|seems|appears)\b",
    re.IGNORECASE,
)
_ABSOLUTES = re.compile(
    r"\b(definitely|certainly|always|never|guaranteed|without doubt)\b",
    re.IGNORECASE,
)

BANDS = ((0.85, "high"), (0.6, "moderate"), (0.35, "low"))


class ConfidenceScorer:
    """Turns evidence signals into a calibrated confidence value."""

    def score(
        self,
        answer: str = "",
        evidence: Optional[Sequence[Any]] = None,
        agreement: Optional[float] = None,
        model_used: bool = False,
        verified: Optional[bool] = None,
    ) -> Dict[str, Any]:
        reasons = []
        value = 0.5

        text = str(answer or "").strip()
        if not text:
            return {"score": 0.0, "band": "none",
                    "reasons": ["there is no answer to score"]}

        count = len(evidence or ())
        if count >= 4:
            value += 0.2
            reasons.append("%d independent sources" % count)
        elif count >= 2:
            value += 0.1
            reasons.append("%d sources" % count)
        elif count == 0:
            value -= 0.1
            reasons.append("no supporting evidence")

        if agreement is not None:
            value += (float(agreement) - 0.5) * 0.3
            reasons.append("source agreement %.0f%%" % (float(agreement) * 100))

        if verified is True:
            value += 0.2
            reasons.append("result was verified")
        elif verified is False:
            value -= 0.3
            reasons.append("verification failed")

        hedges = len(_HEDGES.findall(text))
        if hedges:
            value -= min(0.05 * hedges, 0.2)
            reasons.append("%d hedging phrase(s)" % hedges)

        if _ABSOLUTES.search(text) and count < 2:
            value -= 0.1
            reasons.append("absolute claim without evidence")

        if model_used and count == 0:
            value -= 0.1
            reasons.append("model answer with no external check")

        if len(text) < 15:
            value -= 0.05
            reasons.append("very short answer")

        value = max(0.0, min(1.0, round(value, 3)))
        band = "very low"
        for threshold, name in BANDS:
            if value >= threshold:
                band = name
                break

        return {"score": value, "band": band, "reasons": reasons}

    def should_ask(self, result: Dict[str, Any], threshold: float = 0.35) -> bool:
        """True when confidence is too low to answer without checking."""
        return float(result.get("score", 0.0)) < threshold


confidence = ConfidenceScorer()


def score(answer: str, **signals: Any) -> Dict[str, Any]:
    return confidence.score(answer, **signals)
