"""
Learning Manager — orchestrates JARVIS's self-learning capabilities.

Tracks:
- Command patterns and frequency
- User preferences
- Success/failure outcomes
- Time-of-day usage patterns
- Topic interests
"""

import json
import os
import time
from collections import defaultdict
from pathlib import Path
from threading import Lock


_DATA_DIR = Path(__file__).parent / "data"
_DATA_FILE = _DATA_DIR / "learning.json"
_LOCK = Lock()


class LearningManager:

    def __init__(self):
        self._stats = {
            "total_commands": 0,
            "successful_commands": 0,
            "failed_commands": 0,
            "by_intent": defaultdict(int),
            "by_hour": defaultdict(int),
            "topics": defaultdict(int),
            "last_command": None,
            "last_outcome": None,
            "start_time": time.time(),
        }
        self._load()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def record(self, command: str, decision: str, success: bool) -> None:
        """Record a command and its outcome for learning."""
        with _LOCK:
            self._stats["total_commands"] += 1
            if success:
                self._stats["successful_commands"] += 1
            else:
                self._stats["failed_commands"] += 1
            self._stats["by_intent"][decision] += 1
            self._stats["by_hour"][time.localtime().tm_hour] += 1
            self._stats["last_command"] = command
            self._stats["last_outcome"] = "success" if success else "failure"
            self._save()

    def favourite_app(self) -> str:
        """Return the most-used app/intent."""
        by_intent = self._stats.get("by_intent", {})
        if not by_intent:
            return "unknown"
        return max(by_intent, key=by_intent.get)

    def favourite_command(self) -> str:
        """Return the last executed command."""
        return self._stats.get("last_command", "unknown")

    def success_rate(self) -> float:
        """Return the fraction of successful commands (0.0–1.0)."""
        total = self._stats["total_commands"]
        if total == 0:
            return 0.0
        return round(self._stats["successful_commands"] / total, 3)

    def report(self) -> dict:
        """Return a full learning report."""
        return {
            "total_commands": self._stats["total_commands"],
            "successful": self._stats["successful_commands"],
            "failed": self._stats["failed_commands"],
            "success_rate": self.success_rate(),
            "favourite_app": self.favourite_app(),
            "favourite_command": self.favourite_command(),
            "uptime_seconds": int(time.time() - self._stats["start_time"]),
            "by_intent": dict(self._stats.get("by_intent", {})),
            "by_hour": {str(k): v for k, v in
                        self._stats.get("by_hour", {}).items()},
        }

    def reset(self) -> None:
        """Clear all learning data."""
        with _LOCK:
            self._stats = {
                "total_commands": 0,
                "successful_commands": 0,
                "failed_commands": 0,
                "by_intent": defaultdict(int),
                "by_hour": defaultdict(int),
                "topics": defaultdict(int),
                "last_command": None,
                "last_outcome": None,
                "start_time": time.time(),
            }
            self._save()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load(self):
        try:
            _DATA_DIR.mkdir(parents=True, exist_ok=True)
            if _DATA_FILE.exists():
                with open(_DATA_FILE, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                    self._stats = {
                        k: (dict(v) if isinstance(v, dict) else v)
                        for k, v in raw.items()
                    }
                    # Re-hydrate defaultdict keys
                    for key in ("by_intent", "by_hour", "topics"):
                        if key in self._stats and not isinstance(
                                self._stats[key], defaultdict):
                            self._stats[key] = defaultdict(
                                int, self._stats[key])
        except Exception:
            pass  # Start fresh on corruption

    def _save(self):
        try:
            _DATA_DIR.mkdir(parents=True, exist_ok=True)
            with open(_DATA_FILE, "w", encoding="utf-8") as f:
                json.dump(self._stats, f, ensure_ascii=False, indent=2)
        except Exception:
            pass  # Non-fatal


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_manager = LearningManager()


def record(command, decision, success):
    _manager.record(command, decision, success)


def report():
    return _manager.report()


def favourite_app():
    return _manager.favourite_app()


def favourite_command():
    return _manager.favourite_command()


def success_rate():
    return _manager.success_rate()


def reset():
    _manager.reset()
