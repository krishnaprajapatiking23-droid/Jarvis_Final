"""
==========================================
JARVIS PRO
Behaviour learning
==========================================

Roadmap section 23 (behaviour learning) and the PATTERN stage of section 42.

This file was an empty stub in the project. It now mines the experience store
for real patterns: which requests you make most, when you make them, what
keeps failing and which strategies work.

    from learning.behaviour import behaviour

    behaviour.patterns()          # what JARVIS has noticed
    behaviour.routine()           # time-of-day habits
    behaviour.weak_spots()        # what keeps failing
    behaviour.summary()           # speakable summary

Nothing here calls a model or the network, so it is instant and offline.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Any


MIN_OCCURRENCES = 3
STRONG_FAILURE_RATE = 50.0


class BehaviourLearner:
    """Finds repeatable patterns in what the owner asks for."""

    # ---------------------------------------------------- data

    def _records(self, limit: int = 500) -> list[dict[str, Any]]:
        try:
            from memory.experience import experience

            return experience.recent(limit)

        except Exception:
            return []

    def _part_of_day(self, timestamp: float) -> str:
        hour = datetime.fromtimestamp(timestamp).hour

        if hour < 12:
            return "morning"

        if hour < 17:
            return "afternoon"

        if hour < 21:
            return "evening"

        return "night"

    # ---------------------------------------------------- patterns

    def patterns(self, limit: int = 10) -> list[dict[str, Any]]:
        """Requests that repeat often enough to count as a habit."""

        records = self._records()

        if not records:
            return []

        counts = Counter(
            str(row.get("signature") or "").strip()
            for row in records
            if str(row.get("signature") or "").strip()
        )

        found: list[dict[str, Any]] = []

        for signature, times in counts.most_common(limit * 2):
            if times < MIN_OCCURRENCES:
                continue

            matching = [
                row for row in records if row.get("signature") == signature
            ]
            successes = sum(1 for row in matching if row.get("success"))
            moments = Counter(
                self._part_of_day(float(row.get("at") or 0)) for row in matching
            )
            example = next(
                (str(row.get("goal") or "") for row in matching), signature
            )

            found.append(
                {
                    "pattern": signature,
                    "example": example,
                    "times": times,
                    "success_rate": round(successes / len(matching) * 100, 1),
                    "usual_time": moments.most_common(1)[0][0],
                    "confidence": round(min(times / 10, 1.0), 2),
                }
            )

            if len(found) >= limit:
                break

        return found

    def routine(self) -> dict[str, list[str]]:
        """What you typically ask for at each part of the day."""

        buckets: dict[str, Counter] = {}

        for row in self._records():
            moment = self._part_of_day(float(row.get("at") or 0))
            signature = str(row.get("signature") or "").strip()

            if signature:
                buckets.setdefault(moment, Counter())[signature] += 1

        return {
            moment: [name for name, _ in counter.most_common(3)]
            for moment, counter in buckets.items()
        }

    def weak_spots(self, limit: int = 5) -> list[dict[str, Any]]:
        """Request types that fail more than they succeed."""

        records = self._records()
        grouped: dict[str, list[dict[str, Any]]] = {}

        for row in records:
            signature = str(row.get("signature") or "").strip()

            if signature:
                grouped.setdefault(signature, []).append(row)

        weak: list[dict[str, Any]] = []

        for signature, rows in grouped.items():
            if len(rows) < 2:
                continue

            failures = [row for row in rows if not row.get("success")]
            rate = len(failures) / len(rows) * 100

            if rate >= STRONG_FAILURE_RATE:
                weak.append(
                    {
                        "pattern": signature,
                        "attempts": len(rows),
                        "failure_rate": round(rate, 1),
                        "common_error": Counter(
                            str(row.get("error") or "unknown") for row in failures
                        ).most_common(1)[0][0],
                    }
                )

        weak.sort(key=lambda item: item["failure_rate"], reverse=True)

        return weak[:limit]

    def preferred_strategies(self) -> dict[str, str]:
        """The strategy that works best for each repeated request."""

        try:
            from memory.experience import experience

        except Exception:
            return {}

        chosen: dict[str, str] = {}

        for pattern in self.patterns(limit=10):
            best = experience.best_strategy(pattern["example"])

            if best:
                chosen[pattern["pattern"]] = best

        return chosen

    # ---------------------------------------------------- output

    def predict_next(self) -> list[str]:
        """What you are likely to ask for right now, based on habit."""

        moment = self._part_of_day(datetime.now().timestamp())
        routine = self.routine().get(moment, [])

        return routine[:3]

    def summary(self) -> str:
        """Short spoken-style summary of what has been learned."""

        patterns = self.patterns(limit=3)
        weak = self.weak_spots(limit=2)

        if not patterns and not weak:
            return (
                "I have not seen enough activity yet to learn your habits."
            )

        lines: list[str] = []

        if patterns:
            lines.append("Habits I have noticed:")

            for item in patterns:
                lines.append(
                    f"- '{item['example']}' - {item['times']} times, "
                    f"usually in the {item['usual_time']}, "
                    f"{item['success_rate']}% successful."
                )

        if weak:
            lines.append("What I struggle with:")

            for item in weak:
                lines.append(
                    f"- '{item['pattern']}' fails {item['failure_rate']}% "
                    f"of the time ({item['common_error']})."
                )

        return "\n".join(lines)

    def status(self) -> dict[str, Any]:
        return {
            "records": len(self._records()),
            "patterns_found": len(self.patterns()),
            "weak_spots": len(self.weak_spots()),
            "routine": self.routine(),
        }


behaviour = BehaviourLearner()
