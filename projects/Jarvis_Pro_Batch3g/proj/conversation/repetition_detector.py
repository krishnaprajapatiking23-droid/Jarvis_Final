"""
==========================================
JARVIS PRO
Repetition & Cliche Detector  (variation features 5, 15, 18)
==========================================

Measures how close a candidate reply is to what JARVIS recently said and
strips the chatbot tics that make an assistant sound like a template.

Nothing here invents wording; it only *detects* and *removes*.  Fresh
phrasing always comes from the model.
"""

from __future__ import annotations

import difflib
import re
from typing import Any, Dict, Iterable, List, Sequence

# Two replies above this similarity count as "the same answer again".
THRESHOLD = 0.82

# Number of leading words that make up a reply's "opening".
OPENING_WORDS = 4

# Chatbot cliches: pattern -> what it is replaced with.
CLICHE_PATTERNS: Sequence[tuple] = (
    # reasoning traces some local models emit
    (r"<think>.*?</think>", ""),
    (r"<thinking>.*?</thinking>", ""),
    # "as an AI language model" and the rest of the disclaimer family
    (
        r"as an ai(?: language model| assistant)?,?\s*"
        r"(?:i can say|i must say|i should note|i can tell you)?,?\s*",
        "",
    ),
    (r"as a (?:large )?language model,?\s*", ""),
    # canned openers
    (r"^(certainly|absolutely|of course|sure thing|great question|"
     r"excellent question|good question|no problem|awesome question)"
     r"[!,.:\s]+", ""),
    (r"^i'?d be (happy|glad|delighted) to [^.!?]*[.!?]\s*", ""),
    (r"^let'?s (dive in|dive right in|get started|jump in)[^.!?]*[.!?]\s*", ""),
    (r"^here'?s a (comprehensive|complete|detailed|full) "
     r"(breakdown|overview|explanation)[^.!?:]*[.!?:]\s*", ""),
    (r"^(sure|okay|alright)[!,]\s+(?=here)", ""),
    # canned closers
    (r"\s*(i )?hope (this|that) helps[^.!?]*[.!?]\s*$", ""),
    (r"\s*let me know if you (need|have|want)[^.!?]*[.!?]\s*$", ""),
    (r"\s*feel free to ask[^.!?]*[.!?]\s*$", ""),
    (r"\s*i'?m here whenever you need me[^.!?]*[.!?]?\s*$", ""),
    (r"\s*(let's|we'll) (continue|keep) (building|improving)[^.!?]*[.!?]\s*$", ""),
    (r"\s*happy to help[!.]?\s*$", ""),
)

# Phrases that should never appear automatically in every answer.
CLICHES = (
    "certainly",
    "absolutely",
    "great question",
    "of course",
    "sure thing",
    "i'd be happy to",
    "let's dive in",
    "here's a comprehensive breakdown",
    "hope this helps",
    "as an ai",
    "as a language model",
    "i'm just an ai",
    "it's important to note",
    "it is important to note",
    "delve into",
)

_WORD = re.compile(r"[a-z0-9']+")


def _tokens(text: str) -> List[str]:
    return _WORD.findall((text or "").lower())


def similarity(first: str, second: str) -> float:
    """0.0 - 1.0 similarity between two replies."""
    if not first or not second:
        return 0.0

    left = " ".join(_tokens(first))
    right = " ".join(_tokens(second))
    if not left or not right:
        return 0.0
    if left == right:
        return 1.0

    left_set = set(left.split())
    right_set = set(right.split())
    union = left_set | right_set
    overlap = len(left_set & right_set) / len(union) if union else 0.0
    ratio = difflib.SequenceMatcher(None, left, right).ratio()
    return round((0.5 * overlap) + (0.5 * ratio), 4)


def opening_of(text: str) -> str:
    """Normalised first few words, used to spot a reused opening."""
    words = _tokens(text)[:OPENING_WORDS]
    return " ".join(words)


def closing_of(text: str) -> str:
    """Normalised last sentence, used to spot a reused closing line."""
    sentences = [part.strip() for part in re.split(r"[.!?]+", text or "") if part.strip()]
    if not sentences:
        return ""
    return " ".join(_tokens(sentences[-1]))


def found_cliches(text: str) -> List[str]:
    """Which chatbot cliches appear in the text."""
    lowered = (text or "").lower()
    return [phrase for phrase in CLICHES if phrase in lowered]


def strip_cliches(text: str) -> str:
    """Remove model reasoning traces and canned opener/closer lines."""
    cleaned = (text or "").strip()
    if not cleaned:
        return ""

    for pattern, replacement in CLICHE_PATTERNS:
        cleaned = re.sub(
            pattern,
            replacement,
            cleaned,
            flags=re.IGNORECASE | re.DOTALL,
        )

    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()

    # Re-capitalise if a stripped opener left a lowercase start.
    if cleaned and cleaned[0].islower() and not cleaned.startswith(("i ", "i'")):
        cleaned = cleaned[0].upper() + cleaned[1:]

    return cleaned


def check(
    candidate: str,
    recent_answers: Iterable[str] = (),
    recent_openings: Iterable[str] = (),
    threshold: float = THRESHOLD,
) -> Dict[str, Any]:
    """Report how repetitive ``candidate`` is against recent replies."""
    answers = [answer for answer in recent_answers if answer]
    openings = [opening for opening in recent_openings if opening]

    best_score = 0.0
    closest = ""
    for answer in answers:
        score = similarity(candidate, answer)
        if score > best_score:
            best_score = score
            closest = answer

    opening = opening_of(candidate)

    return {
        "repetitive": best_score >= threshold,
        # the same flag under the shorter name some callers use
        "repeat": best_score >= threshold,
        "score": best_score,
        "closest": closest,
        "opening": opening,
        "reused_opening": bool(opening) and opening in openings,
        "cliches": found_cliches(candidate),
    }


__all__ = [
    "THRESHOLD",
    "CLICHES",
    "similarity",
    "opening_of",
    "closing_of",
    "found_cliches",
    "strip_cliches",
    "check",
]
