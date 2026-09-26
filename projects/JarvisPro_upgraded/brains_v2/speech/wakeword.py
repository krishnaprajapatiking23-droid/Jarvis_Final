"""Wake-word detection over a text transcript (roadmap section 29).

Audio capture belongs to the voice backend; this module owns the decision of
whether a transcript actually addressed Jarvis, which is testable offline.
"""

from __future__ import annotations

import difflib
import re
from typing import Any, Dict, List, Optional

__all__ = ["WakeWord", "wake_word", "detect"]

DEFAULT_WORDS = ("jarvis", "hey jarvis", "ok jarvis", "javis", "jervis")
FUZZY_THRESHOLD = 0.82


class WakeWord:
    """Decides whether a transcript is addressed to Jarvis."""

    def __init__(self, words: Optional[List[str]] = None,
                 threshold: float = FUZZY_THRESHOLD):
        self.words = [w.lower() for w in (words or DEFAULT_WORDS)]
        self.threshold = threshold

    def add(self, word: str) -> None:
        word = str(word).strip().lower()
        if word and word not in self.words:
            self.words.append(word)

    def detect(self, transcript: str) -> Dict[str, Any]:
        text = " ".join(str(transcript or "").lower().split())

        if not text:
            return {"awake": False, "word": "", "command": "", "confidence": 0.0}

        for word in sorted(self.words, key=len, reverse=True):
            if text.startswith(word):
                return {"awake": True, "word": word,
                        "command": self._strip(text[len(word):]),
                        "confidence": 1.0}

        for word in self.words:
            if re.search(r"\b%s\b" % re.escape(word), text):
                remainder = re.sub(r"\b%s\b" % re.escape(word), " ", text, count=1)
                return {"awake": True, "word": word,
                        "command": self._strip(remainder), "confidence": 0.95}

        # Speech recognition mangles the name; allow a close match on word one.
        first = text.split()[0]
        best, score = "", 0.0
        for word in self.words:
            ratio = difflib.SequenceMatcher(None, first, word.split()[-1]).ratio()
            if ratio > score:
                best, score = word, ratio

        if score >= self.threshold:
            return {"awake": True, "word": best,
                    "command": self._strip(text[len(first):]),
                    "confidence": round(score, 3)}

        return {"awake": False, "word": "", "command": "",
                "confidence": round(score, 3)}

    @staticmethod
    def _strip(text: str) -> str:
        return re.sub(r"^[\s,.:;-]+", "", text).strip()


wake_word = WakeWord()


def detect(transcript: str) -> Dict[str, Any]:
    return wake_word.detect(transcript)
