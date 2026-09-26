"""
Self-Correction Engine — detects and fixes malformed or ambiguous commands.
Used by brains_v2/manager.py when a command fails verification.
"""

import re
from threading import Lock


class SelfCorrection:

    # Common typo/ambiguity corrections
    REPLACEMENTS = [
        # Typos
        (r"\bteh\b", "the"),
        (r"\brecieve\b", "receive"),
        (r"\boccured\b", "occurred"),
        (r"\bseperate\b", "separate"),
        (r"\bdefinately\b", "definitely"),
        (r"\boccurence\b", "occurrence"),
        (r"\brecomend\b", "recommend"),
        (r"\bacheive\b", "achieve"),
        # Ambiguous shortcuts
        (r"\bok\b", "okay"),
        (r"\bplz\b", "please"),
        (r"\bpls\b", "please"),
        (r"\bthx\b", "thanks"),
        (r"\bty\b", "thank you"),
        (r"\bw/\b", "with"),
        (r"\bb4\b", "before"),
        (r"\b2day\b", "today"),
        (r"\b2morrow\b", "tomorrow"),
        # Double spaces / punctuation noise
        (r"\s{2,}", " "),
        (r"[.]{3,}", "..."),
    ]

    def __init__(self):
        self.total = 0
        self.corrected = 0
        self._history = []
        self._lock = Lock()

    def correct(self, command: str) -> str:
        """Apply all correction passes to a command string."""
        self.total += 1
        if not isinstance(command, str):
            return ""

        original = command.strip()
        corrected = original

        for pattern, replacement in self.REPLACEMENTS:
            corrected = re.sub(pattern, replacement, corrected,
                               flags=re.IGNORECASE)

        # Normalise extra whitespace
        corrected = re.sub(r"\s+", " ", corrected).strip()

        if corrected != original:
            self.corrected += 1
            with self._lock:
                self._history.append({"original": original,
                                       "corrected": corrected})

        return corrected

    def statistics(self) -> dict:
        return {
            "total": self.total,
            "corrected": self.corrected,
            "correction_rate": (
                round(self.corrected / self.total, 3)
                if self.total > 0 else 0.0
            ),
            "recent": self._history[-5:],
        }

    def reset(self) -> None:
        with self._lock:
            self._history.clear()
            self.total = 0
            self.corrected = 0


self_correction = SelfCorrection()