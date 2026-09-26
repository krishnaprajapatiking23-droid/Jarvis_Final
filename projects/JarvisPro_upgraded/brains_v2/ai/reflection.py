"""Self-reflection over past turns (roadmap sections 20, 21 and 41)."""

from __future__ import annotations

import json
import os
from collections import Counter
from datetime import datetime
from typing import Any, Dict, List, Optional

__all__ = ["Reflection", "reflection"]

STORE = os.path.join("data", "reflection.json")
MAX_TURNS = 500


class Reflection:
    """Keeps a rolling record of outcomes and turns it into observations."""

    def __init__(self, path: Optional[str] = None):
        self.path = path or STORE
        self._turns: List[Dict[str, Any]] = []
        self.load()

    def load(self) -> None:
        if not os.path.exists(self.path):
            return
        try:
            with open(self.path, "r", encoding="utf-8") as handle:
                stored = json.load(handle)
            if isinstance(stored, list):
                self._turns = stored[-MAX_TURNS:]
        except (OSError, json.JSONDecodeError):
            self._turns = []

    def save(self) -> None:
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as handle:
            json.dump(self._turns[-MAX_TURNS:], handle, indent=2)

    def record(self, command: str, route: str, success: bool,
               reason: str = "") -> None:
        self._turns.append({
            "command": str(command)[:200],
            "route": route,
            "success": bool(success),
            "reason": reason,
            "at": datetime.now().isoformat(timespec="seconds"),
        })
        self._turns = self._turns[-MAX_TURNS:]
        self.save()

    # -- analysis ----------------------------------------------------
    def success_rate(self) -> float:
        if not self._turns:
            return 0.0
        wins = sum(1 for turn in self._turns if turn["success"])
        return round(wins * 100.0 / len(self._turns), 1)

    def weakest_routes(self, minimum: int = 3) -> List[Dict[str, Any]]:
        totals: Counter = Counter()
        failures: Counter = Counter()
        for turn in self._turns:
            totals[turn["route"]] += 1
            if not turn["success"]:
                failures[turn["route"]] += 1

        weak = []
        for route, total in totals.items():
            if total < minimum:
                continue
            rate = failures[route] * 100.0 / total
            if rate >= 25.0:
                weak.append({"route": route, "attempts": total,
                             "failure_rate": round(rate, 1)})
        return sorted(weak, key=lambda item: -item["failure_rate"])

    def repeated_failures(self, minimum: int = 2) -> List[Dict[str, Any]]:
        counter: Counter = Counter(
            turn["command"].lower() for turn in self._turns if not turn["success"])
        return [{"command": command, "times": times}
                for command, times in counter.most_common(10) if times >= minimum]

    def observations(self) -> List[str]:
        notes: List[str] = []
        rate = self.success_rate()
        if self._turns:
            notes.append("Success rate is %.1f%% over %d turns."
                         % (rate, len(self._turns)))
        for weak in self.weakest_routes():
            notes.append("The %s route fails %.0f%% of the time (%d attempts)."
                         % (weak["route"], weak["failure_rate"], weak["attempts"]))
        for repeat in self.repeated_failures():
            notes.append("%r has failed %d times -- worth a different approach."
                         % (repeat["command"], repeat["times"]))
        if not notes:
            notes.append("Not enough history to draw a conclusion yet.")
        return notes

    def report(self) -> Dict[str, Any]:
        return {
            "turns": len(self._turns),
            "success_rate": self.success_rate(),
            "weak_routes": self.weakest_routes(),
            "repeated_failures": self.repeated_failures(),
            "observations": self.observations(),
        }


reflection = Reflection()
