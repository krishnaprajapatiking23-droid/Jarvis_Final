"""
==========================================
JARVIS PRO
Response Quality Check  (variation features 18, 27)
==========================================

The last gate before a reply leaves JARVIS.  It checks the draft against
the plan and against what was recently said, and returns a directive the
generator can feed back into the model for one more attempt.

Retries are bounded by :data:`MAX_RETRIES` - there is no regeneration
loop.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable, List

from conversation import repetition_detector
from conversation.output_sanitizer import looks_internal

# At most this many extra generation attempts (27).
MAX_RETRIES = 2

# Draft is "the same answer again" at or above this similarity (18).
REPEAT_THRESHOLD = repetition_detector.THRESHOLD

# A follow-up answer may not overlap the previous answer more than this.
RESTATE_THRESHOLD = 0.55

# Length envelopes per depth, in characters.
LENGTH_LIMITS = {
    "one_line": (0, 240),
    "short": (0, 700),
    "normal": (0, 2600),
    "deep": (160, 8000),
}

# Replies that mean "the model was unavailable" - never worth retrying.
UNAVAILABLE = (
    "ollama is offline",
    "empty response received",
    "invalid response from ollama",
    "no response received",
    # brains_v2/llm/ollama_provider.py -> STATUS_MESSAGES
    "i couldn't reach the language model",
    "the language model is not installed",
    "the model took too long to answer",
    "the language model failed",
    "the model returned something i couldn't read",
    "the model returned an empty answer",
)

def is_unavailable(text) -> bool:
    """True when ``text`` is a model-unavailable status, not an answer.

    Used by the dialogue manager and the engine so a technical failure is
    never decorated ("As I mentioned, ..."), never stored as something
    JARVIS said, and never retried in a loop.
    """

    lowered = str(text or "").strip().lower()

    if not lowered:
        return False

    return any(marker in lowered for marker in UNAVAILABLE)


HARD_ISSUES = {
    "internal_content",
    "repeats_recent",
    "repeats_previous_answer",
    "restates_previous",
    "reused_opening",
    "too_long",
    "too_short",
}


@dataclass
class QualityReport:
    """Outcome of the quality gate for one draft."""

    ok: bool = True
    issues: List[str] = field(default_factory=list)
    directive: str = ""
    score: float = 0.0
    unavailable: bool = False

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "issues": list(self.issues),
            "directive": self.directive,
            "score": self.score,
            "unavailable": self.unavailable,
        }


def _sentences(text: str) -> List[str]:
    return [part.strip() for part in re.split(r"[.!?]+", text or "") if part.strip()]


def _directive_for(issues: Iterable[str]) -> str:
    """One short instruction that addresses the detected problems."""
    issues = list(issues)
    parts: List[str] = []

    if "repeats_recent" in issues or "repeats_previous_answer" in issues:
        parts.append(
            "That draft repeats an answer you already gave. Keep the facts "
            "identical but rewrite it: different opening, different sentence "
            "order, and one detail you have not mentioned yet."
        )
    if "restates_previous" in issues:
        parts.append(
            "Do not re-explain what you already covered. Answer only the new "
            "part of the question."
        )
    if "reused_opening" in issues:
        parts.append("Start with different words than your last reply.")
    if "too_long" in issues:
        parts.append("That was too long for what was asked. Cut it right down.")
    if "too_short" in issues:
        parts.append(
            "The user asked for detail. Expand it properly and include an example."
        )
    if "cliche" in issues:
        parts.append("Drop the stock assistant phrases.")

    return " ".join(parts)


def check(
    text: str,
    plan: Any = None,
    recent_answers: Iterable[str] = (),
    recent_openings: Iterable[str] = (),
    previous_answer: str = "",
) -> QualityReport:
    """Evaluate a draft reply. Never raises."""
    draft = (text or "").strip()
    if not draft:
        return QualityReport(
            ok=False,
            issues=["empty"],
            directive="Answer the question directly.",
        )

    lowered = draft.lower()
    if any(marker in lowered for marker in UNAVAILABLE):
        # The model is down; retrying cannot help and must not loop.
        return QualityReport(ok=True, issues=["unavailable"], unavailable=True)

    # Reasoning, planning scaffolds and prompt sections are never an answer.
    if looks_internal(draft):
        return QualityReport(
            ok=False,
            issues=["internal_content"],
            directive=(
                "Reply with the final answer only - no reasoning, no planning "
                "notes and no section headings."
            ),
        )

    depth = getattr(plan, "depth", "normal")
    factual = bool(getattr(plan, "factual", False))
    build_on_previous = bool(getattr(plan, "build_on_previous", False))

    issues: List[str] = []

    report = repetition_detector.check(draft, recent_answers, recent_openings)
    if report["repetitive"]:
        issues.append("repeats_recent")
    if report["reused_opening"]:
        issues.append("reused_opening")
    if report["cliches"]:
        issues.append("cliche")

    previous_answer = (previous_answer or "").strip()
    if previous_answer:
        overlap = repetition_detector.similarity(draft, previous_answer)
        if overlap >= REPEAT_THRESHOLD:
            issues.append("repeats_previous_answer")
        elif build_on_previous and overlap >= RESTATE_THRESHOLD:
            issues.append("restates_previous")

    # Length envelope (8).  Factual answers are exempt: "4." is correct.
    if not factual:
        minimum, maximum = LENGTH_LIMITS.get(depth, LENGTH_LIMITS["normal"])
        if len(draft) > maximum:
            issues.append("too_long")
        elif len(draft) < minimum:
            issues.append("too_short")
        if depth == "one_line" and len(_sentences(draft)) > 2:
            if "too_long" not in issues:
                issues.append("too_long")

    hard = [issue for issue in issues if issue in HARD_ISSUES]

    return QualityReport(
        ok=not hard,
        issues=issues,
        directive=_directive_for(issues),
        score=float(report["score"]),
    )


__all__ = [
    "QualityReport",
    "MAX_RETRIES",
    "REPEAT_THRESHOLD",
    "RESTATE_THRESHOLD",
    "LENGTH_LIMITS",
    "check",
]
