"""
Self-Improvement Engine — builds a backlog of improvements from failures.
Used by brains_v2/manager.py after each failed verification.
"""

import json
import time
from pathlib import Path
from threading import Lock


_DATA_FILE = Path(__file__).parent.parent / "data" / "improvements.json"
_LOCK = Lock()


class SelfImprovement:

    def __init__(self):
        self.version = "2.0"
        self.improvements = []
        self._load()

    def learn(self, command: str, verification: dict) -> None:
        """Record a failure for future improvement review."""
        if verification.get("success", True):
            return

        entry = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "command": command,
            "decision": verification.get("decision", "unknown"),
            "error": verification.get("error", "unknown failure"),
        }
        with _LOCK:
            self.improvements.append(entry)
            self._save()

    def suggestions(self, limit: int = 10) -> list:
        """Return the most recent improvement suggestions."""
        return self.improvements[-limit:]

    def clear(self) -> None:
        with _LOCK:
            self.improvements.clear()
            self._save()

    def report(self) -> dict:
        return {
            "version": self.version,
            "total": len(self.improvements),
            "pending": len(self.improvements),
            "items": self.suggestions(),
        }

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load(self):
        try:
            _DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
            if _DATA_FILE.exists():
                with open(_DATA_FILE, "r", encoding="utf-8") as f:
                    self.improvements = json.load(f)
        except Exception:
            self.improvements = []

    def _save(self):
        try:
            _DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(_DATA_FILE, "w", encoding="utf-8") as f:
                json.dump(self.improvements, f, ensure_ascii=False, indent=2)
        except Exception:
            pass


self_improvement = SelfImprovement()