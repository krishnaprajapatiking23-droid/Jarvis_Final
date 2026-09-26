"""Lightweight semantic embeddings (roadmap section 4).

A hashed bag-of-character-ngrams vector with cosine similarity. It is not a
neural embedding, and it does not pretend to be -- but it is deterministic,
needs no model download and works offline, which is what memory search here
actually requires.
"""

from __future__ import annotations

import math
import re
from typing import Dict, Iterable, List, Sequence, Tuple

__all__ = ["embed", "similarity", "most_similar", "DIMENSIONS"]

DIMENSIONS = 256
NGRAM = 3
_TOKEN = re.compile(r"[a-z0-9]+")
STOPWORDS = frozenset(
    "a an the is are was were be been being of to in on at for with and or "
    "but if then than that this these those it its i you he she we they my "
    "your his her our their do does did have has had will would can could".split()
)


def tokens(text: str) -> List[str]:
    return [t for t in _TOKEN.findall(str(text or "").lower())
            if t not in STOPWORDS]


def _features(text: str) -> Iterable[str]:
    words = tokens(text)
    for word in words:
        yield "w:" + word
        padded = "^%s$" % word
        for index in range(len(padded) - NGRAM + 1):
            yield "g:" + padded[index:index + NGRAM]
    for first, second in zip(words, words[1:]):
        yield "b:%s_%s" % (first, second)


def embed(text: str, dimensions: int = DIMENSIONS) -> List[float]:
    """Deterministic unit-length vector for a piece of text."""
    vector = [0.0] * dimensions

    for feature in _features(text):
        digest = hash(feature) if False else _stable_hash(feature)
        index = digest % dimensions
        sign = 1.0 if (digest >> 16) % 2 == 0 else -1.0
        vector[index] += sign

    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0.0:
        return vector
    return [value / norm for value in vector]


def _stable_hash(text: str) -> int:
    """FNV-1a: stable across processes, unlike Python's salted hash()."""
    value = 0x811C9DC5
    for byte in text.encode("utf-8"):
        value ^= byte
        value = (value * 0x01000193) & 0xFFFFFFFF
    return value


def similarity(first: Sequence[float], second: Sequence[float]) -> float:
    """Cosine similarity of two unit vectors, clamped to 0..1."""
    if len(first) != len(second):
        raise ValueError("vector dimension mismatch: %d vs %d"
                         % (len(first), len(second)))
    dot = sum(a * b for a, b in zip(first, second))
    return round(max(0.0, min(1.0, (dot + 1.0) / 2.0)), 4)


def most_similar(query: str, candidates: Sequence[str],
                 limit: int = 5) -> List[Tuple[str, float]]:
    """Rank candidates by similarity to the query."""
    vector = embed(query)
    scored = [(candidate, similarity(vector, embed(candidate)))
              for candidate in candidates]
    scored.sort(key=lambda pair: -pair[1])
    return scored[:limit]
