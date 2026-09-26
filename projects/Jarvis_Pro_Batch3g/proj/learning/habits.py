"""
==========================================
JARVIS PRO
Habit tracking
==========================================

Roadmap section 23 (behaviour learning) - the proactive half.

This file was an empty stub. It now turns the patterns found by
``learning/behaviour.py`` into concrete, time-aware suggestions, so JARVIS
can offer the thing you usually want before you ask for it.

    from learning.habits import habits

    habits.suggestions()      # what to offer right now
    habits.greeting_hint()    # one line to add to a greeting
"""

from __future__ import annotations

from datetime import datetime
from typing import Any


SUGGESTION_THRESHOLD = 0.4


class HabitTracker:
    """Turns learned patterns into proactive offers."""

    def _patterns(self) -> list[dict[str, Any]]:
        try:
            from learning.behaviour import behaviour

            return behaviour.patterns(limit=10)

        except Exception:
            return []

    def _part_of_day(self) -> str:
        hour = datetime.now().hour

        if hour < 12:
            return "morning"

        if hour < 17:
            return "afternoon"

        if hour < 21:
            return "evening"

        return "night"

    # ---------------------------------------------------- suggestions

    def suggestions(self, limit: int = 3) -> list[dict[str, Any]]:
        """Habits that match the current time of day and usually succeed."""

        moment = self._part_of_day()
        found: list[dict[str, Any]] = []

        for pattern in self._patterns():
            if pattern["usual_time"] != moment:
                continue

            if pattern["confidence"] < SUGGESTION_THRESHOLD:
                continue

            if pattern["success_rate"] < 50:
                continue

            found.append(
                {
                    "suggestion": pattern["example"],
                    "reason": (
                        f"You usually do this in the {moment} "
                        f"({pattern['times']} times so far)."
                    ),
                    "confidence": pattern["confidence"],
                }
            )

        found.sort(key=lambda item: item["confidence"], reverse=True)

        return found[:limit]

    def greeting_hint(self) -> str:
        """A single proactive line for the greeting, or nothing."""

        found = self.suggestions(limit=1)

        if not found:
            return ""

        return f"Shall I {found[0]['suggestion']}? {found[0]['reason']}"

    def most_common(self, limit: int = 5) -> list[str]:
        return [item["example"] for item in self._patterns()[:limit]]

    def status(self) -> dict[str, Any]:
        return {
            "part_of_day": self._part_of_day(),
            "patterns": len(self._patterns()),
            "suggestions_now": len(self.suggestions()),
        }


habits = HabitTracker()
