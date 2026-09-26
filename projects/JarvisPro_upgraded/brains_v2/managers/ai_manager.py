"""AI model manager (roadmap section 35).

Chooses which model should answer, tracks per-model latency and success, and
falls back down a chain when the preferred model is unavailable. It never
pretends a model answered when none did.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Callable, Dict, List, Optional

from brains_v2.managers.base import BaseManager, ManagerResult

__all__ = ["AIManager", "ai_manager", "ModelRecord"]

log = logging.getLogger("jarvis.ai")

#: Task kind -> ordered model preference.
ROUTING = {
    "coding": ("coding", "strong", "general"),
    "research": ("research", "strong", "general"),
    "vision": ("vision", "general"),
    "conversation": ("light", "general", "strong"),
    "reasoning": ("strong", "general"),
}


class ModelRecord:
    """Live statistics for one registered model."""

    __slots__ = ("name", "role", "handler", "calls", "failures", "total_latency")

    def __init__(self, name: str, role: str, handler: Callable[[str], Any]):
        self.name = name
        self.role = role
        self.handler = handler
        self.calls = 0
        self.failures = 0
        self.total_latency = 0.0

    @property
    def average_latency(self) -> float:
        return round(self.total_latency / self.calls, 3) if self.calls else 0.0

    @property
    def success_rate(self) -> float:
        if not self.calls:
            return 0.0
        return round((self.calls - self.failures) * 100.0 / self.calls, 1)

    def to_dict(self) -> Dict[str, Any]:
        return {"name": self.name, "role": self.role, "calls": self.calls,
                "failures": self.failures, "success_rate": self.success_rate,
                "average_latency": self.average_latency}


class AIManager(BaseManager):
    capability = "ai"
    description = "Selects, calls and scores the available language models."

    def __init__(self) -> None:
        self._models: Dict[str, ModelRecord] = {}
        self._bootstrapped = False

    def register(self, name: str, role: str, handler: Callable[[str], Any]) -> None:
        self._models[name] = ModelRecord(name, role, handler)

    def bootstrap(self) -> None:
        if self._bootstrapped:
            return
        self._bootstrapped = True
        try:
            from brains_v2.llm.manager import ask

            for role in ("general", "light", "strong", "coding", "research"):
                self.register(role, role, ask)
        except Exception as error:
            log.info("no language model backend available: %s", error)

    def models(self) -> List[Dict[str, Any]]:
        self.bootstrap()
        return [record.to_dict() for record in self._models.values()]

    def choose(self, kind: str = "conversation") -> List[ModelRecord]:
        self.bootstrap()
        order = ROUTING.get(kind, ROUTING["conversation"])
        chosen = [self._models[name] for name in order if name in self._models]
        chosen.extend(r for r in self._models.values() if r not in chosen)
        return chosen

    def ask(self, prompt: str, kind: str = "conversation") -> Dict[str, Any]:
        """Try each candidate model in order; report honestly if all fail."""
        errors: List[str] = []

        for record in self.choose(kind):
            started = time.time()
            record.calls += 1
            try:
                answer = record.handler(prompt)
            except Exception as error:
                record.failures += 1
                errors.append("%s: %s" % (record.name, error))
                continue
            finally:
                record.total_latency += time.time() - started

            if answer:
                return ManagerResult(True, str(answer), model=record.name,
                                     latency=round(time.time() - started, 3))

            record.failures += 1
            errors.append("%s returned nothing" % record.name)

        return ManagerResult(
            False,
            "No language model is available right now.",
            errors=errors,
        )

    def can_handle(self, command: Any) -> bool:
        self.bootstrap()
        return bool(self._models)

    def execute(self, command: Any, **context: Any) -> Dict[str, Any]:
        return self.ask(str(command or ""), context.get("kind", "conversation"))

    def health(self) -> Dict[str, Any]:
        self.bootstrap()
        return {"available": bool(self._models), "capability": self.capability,
                "detail": "%d model role(s) registered" % len(self._models)}


ai_manager = AIManager()
