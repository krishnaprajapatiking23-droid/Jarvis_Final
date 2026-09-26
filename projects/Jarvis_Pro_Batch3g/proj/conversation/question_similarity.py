"""
==========================================
JARVIS PRO
Question Similarity  (variation features 2, 3, 32)
==========================================

Decides whether the current message is asking for the *same information*
as something asked earlier - without an external embedding API.

How it works
------------
1. ``normalize()`` folds the message down to a comparable form and
   translates the common Hinglish question words, so "Python kya hai?"
   and "What is Python?" become comparable.
2. ``facet()`` classifies *what is being asked* (definition, purpose,
   reason, method, comparison, example, list).  Two questions about the
   same subject but with different facets are different requests:
       "What is Python?"          -> definition
       "What is Python used for?" -> purpose
3. ``subject()`` keeps only the content words, so the phrasing around
   the subject ("can you tell me what X is") stops mattering.

``similarity()`` blends subject overlap with a character-level ratio and
penalises a facet mismatch, which gives a usable semantic score with
nothing but the standard library.
"""

from __future__ import annotations

import difflib
import re
from typing import Dict, List, Set, Tuple

# ------------------------------------------------------------------
# Hinglish / Hindi question words -> English equivalents (3.32)
# ------------------------------------------------------------------
TRANSLATIONS: Tuple[Tuple[str, str], ...] = (
    ("kya hai", "what is"),
    ("kya h", "what is"),
    ("kya hota hai", "what is"),
    ("kaun hai", "who is"),
    ("kis liye", "used for"),
    ("kis kaam", "used for"),
    ("kaam aata", "used for"),
    ("kaam karta", "how does it work"),
    ("kaise kaam", "how does it work"),
    ("kaise", "how"),
    ("kyun", "why"),
    ("kyu", "why"),
    ("kahan", "where"),
    ("kaha", "where"),
    ("kab", "when"),
    ("batao", "tell me"),
    ("bata", "tell me"),
    ("samjhao", "explain"),
    ("samjha do", "explain"),
    ("matlab", "meaning"),
    ("antar", "difference"),
    ("udaharan", "example"),
)

# ------------------------------------------------------------------
# What is being asked (order matters: specific facets first)
# ------------------------------------------------------------------
FACET_PATTERNS: Tuple[Tuple[str, str], ...] = (
    ("purpose", r"\bused for\b|\buse of\b|\buses of\b|\bpurpose\b|"
                r"\bwhat can (i|we|you) (do|build|make)\b|\bwhat for\b"),
    ("comparison", r"\bdifference\b|\bdifferences\b|\bvs\b|\bversus\b|"
                   r"\bcompare\b|\bbetter than\b|\bwhich is better\b"),
    ("reason", r"\bwhy\b|\breason\b|\bpopular\b|\bso good\b|\bso slow\b"),
    ("method", r"\bhow (do|to|can|does|would|should)\b|\bhow it works\b|"
               r"\bhow does it work\b|\bsteps\b|\binstall\b|\bset up\b"),
    ("example", r"\bexample\b|\bexamples\b|\bsample\b|\bshow me code\b"),
    ("list", r"\blist\b|\btypes of\b|\bkinds of\b|\boptions\b|"
             r"\bwhat are the\b"),
    ("definition", r"\bwhat is\b|\bwhat's\b|\bwhats\b|\bwhat exactly\b|"
                   r"\bwho is\b|\bwho's\b|\bexplain\b|\bdefine\b|"
                   r"\btell me about\b|\bmeaning\b|\bwhat does .* mean\b|"
                   r"\bintroduce\b|\boverview\b"),
)

# Words that carry no subject information.
STOPWORDS: Set[str] = {
    "a", "an", "the", "is", "are", "was", "were", "am", "be", "been",
    "do", "does", "did", "can", "could", "would", "should", "will",
    "shall", "may", "might", "must", "i", "me", "my", "mine", "we",
    "our", "you", "your", "it", "its", "this", "that", "these", "those",
    "of", "about", "for", "to", "in", "on", "at", "by", "with", "and",
    "or", "but", "so", "if", "then", "than", "as", "just", "please",
    "tell", "explain", "know", "want", "like", "give", "show", "say",
    "define", "describe", "exactly", "actually", "really", "mean",
    "meaning", "what", "whats", "who", "why", "how", "when", "where",
    "which", "used", "use", "uses", "purpose", "difference", "example",
    "examples", "list", "types", "kinds", "popular", "reason", "work",
    "works", "jarvis", "hai", "ho", "hain", "ka", "ki", "ke", "ko",
    "mujhe", "thoda", "zara", "aur", "kya", "bhi", "na", "ek",
}

QUESTION_MARKERS = (
    "what", "who", "why", "how", "when", "where", "which", "whose",
    "tell me", "explain", "describe", "define", "difference", "kya",
    "kaise", "kyun", "kyu", "batao", "samjhao",
)

SIMILARITY_THRESHOLD = 0.70


def normalize(text: str) -> str:
    """Lowercase, de-punctuate and translate Hinglish question words."""
    if not text:
        return ""
    lowered = text.strip().lower()
    lowered = lowered.replace("?", " ").replace("!", " ")
    lowered = re.sub(r"[^\w\s'+\-*/]", " ", lowered)
    lowered = re.sub(r"\s+", " ", lowered).strip()

    for hinglish, english in TRANSLATIONS:
        if hinglish in lowered:
            lowered = lowered.replace(hinglish, english)

    lowered = re.sub(r"\bcan you\b|\bcould you\b|\bwould you\b", " ", lowered)
    lowered = re.sub(r"\s+", " ", lowered).strip()
    return lowered


# Fallback words meaning "tell me what this is" when no facet pattern hit.
DEFINITION_HINTS = {
    "what", "who", "explain", "tell", "describe", "define", "meaning",
    "about",
}


def facet(text: str) -> str:
    """Which *kind* of information the question asks for."""
    normalized = normalize(text)
    if not normalized:
        return ""
    for name, pattern in FACET_PATTERNS:
        if re.search(pattern, normalized):
            return name
    # "Can you tell me what Python is?" has no sharp marker but is still a
    # definition request, so it must match "What is Python?".
    if set(normalized.split()) & DEFINITION_HINTS:
        return "definition"
    return ""


def subject(text: str) -> Set[str]:
    """Content words of the question - what it is *about*."""
    normalized = normalize(text)
    words = [word for word in normalized.split() if word not in STOPWORDS]
    return {word for word in words if len(word) > 1}


def is_question(text: str) -> bool:
    """True for anything that reads like an information request."""
    if not text:
        return False
    stripped = text.strip()
    if stripped.endswith("?"):
        return True
    normalized = normalize(stripped)
    if any(normalized.startswith(marker) for marker in QUESTION_MARKERS):
        return True
    # Hinglish word order puts the question word in the middle:
    # "Python kya hai" normalises to "python what is".
    padded = f" {normalized} "
    return any(f" {marker} " in padded for marker in QUESTION_MARKERS)


def fingerprint(text: str) -> str:
    """Stable key for "this information request"."""
    tokens = sorted(subject(text))
    return f"{facet(text) or 'other'}|{' '.join(tokens)}"


def similarity(first: str, second: str) -> float:
    """0.0 - 1.0 score for "these ask for the same information"."""
    left = normalize(first)
    right = normalize(second)
    if not left or not right:
        return 0.0
    if left == right:
        return 1.0

    left_subject = subject(first)
    right_subject = subject(second)

    if left_subject or right_subject:
        union = left_subject | right_subject
        overlap = len(left_subject & right_subject) / len(union) if union else 0.0
    else:
        overlap = 0.0

    ratio = difflib.SequenceMatcher(None, left, right).ratio()
    score = (0.65 * overlap) + (0.35 * ratio)

    left_facet = facet(first)
    right_facet = facet(second)
    if left_facet and right_facet and left_facet != right_facet:
        score *= 0.45

    return round(min(score, 1.0), 4)


def same_request(
    first: str,
    second: str,
    threshold: float = SIMILARITY_THRESHOLD,
) -> bool:
    """True when both messages ask for essentially the same information."""
    left_facet = facet(first)
    right_facet = facet(second)
    if left_facet and right_facet and left_facet != right_facet:
        return False
    return similarity(first, second) >= threshold


def most_similar(
    text: str,
    candidates: List[str],
    threshold: float = SIMILARITY_THRESHOLD,
) -> Dict[str, object]:
    """Best matching candidate question, or an empty match."""
    best: Dict[str, object] = {"text": "", "score": 0.0, "index": -1}
    for index, candidate in enumerate(candidates):
        score = similarity(text, candidate)
        if score > float(best["score"]):
            best = {"text": candidate, "score": score, "index": index}
    if float(best["score"]) < threshold:
        return {"text": "", "score": float(best["score"]), "index": -1}
    return best


__all__ = [
    "normalize",
    "facet",
    "subject",
    "is_question",
    "fingerprint",
    "similarity",
    "same_request",
    "most_similar",
    "SIMILARITY_THRESHOLD",
]
