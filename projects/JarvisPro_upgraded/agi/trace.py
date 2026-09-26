"""
==========================================
JARVIS PRO
AGI reasoning trace
==========================================

Roadmap section 75 (reasoning trace) and section 80 (observability).

A trace is the structured record of one pass through the AGI loop: which goal,
which knowledge and memories were consulted, which strategies were considered
and why one was chosen, what was executed, what was observed, whether it
verified, and what was learned.

This deliberately stores *structured metadata*, not free-form model
deliberation. It is an audit record of what the system did, so a failure can be
attributed to a specific stage (section 79).

    from agi.trace import Trace

    trace = Trace.start("make the project ready for release")
    trace.stage("planning", plan=["a", "b"])
    trace.finish("completed", verified=True)
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from core.atomic_json import AtomicJSONStore

# Pipeline stages, in order. Used to attribute a failure to a layer.
STAGES = (
    "input",
    "identity",
    "intent",
    "context",
    "memory",
    "profile",
    "knowledge",
    "world_model",
    "goal",
    "constraints",
    "priority",
    "uncertainty",
    "reasoning",
    "hypotheses",
    "planning",
    "decomposition",
    "selection",
    "safety",
    "execution",
    "observation",
    "verification",
    "reflection",
    "experience",
    "learning",
    "strategy_update",
    "world_update",
    "memory_update",
    "goal_update",
    "report",
)

TRACE_LIMIT = 200


@dataclass
class Step:
    stage: str
    at: float
    duration: float = 0.0
    ok: bool = True
    detail: dict[str, Any] = field(default_factory=dict)

    def report(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "at": self.at,
            "duration": round(self.duration, 4),
            "ok": self.ok,
            "detail": self.detail,
        }


class Trace:
    """One structured pass through the AGI pipeline."""

    _store = AtomicJSONStore("data/agi_traces.json", [])
    _lock = threading.RLock()

    def __init__(self, goal: str, trace_id: str = "") -> None:
        self.id = trace_id or uuid.uuid4().hex[:12]
        self.goal = str(goal)
        self.started = time.time()
        self.finished: float | None = None
        self.status = "running"
        self.steps: list[Step] = []
        self.knowledge_used: list[str] = []
        self.memories_used: list[str] = []
        self.hypotheses: list[str] = []
        self.strategies_considered: list[dict[str, Any]] = []
        self.selected_strategy: str = ""
        self.selection_reason: str = ""
        self.assumptions: list[str] = []
        self.lessons: list[str] = []
        self.confidence: float = 0.0
        self.verified: bool = False
        self.failure_stage: str = ""
        self._open: tuple[str, float] | None = None

    # ------------------------------------------------------------- lifecycle

    @classmethod
    def start(cls, goal: str) -> "Trace":
        return cls(goal)

    def stage(self, name: str, ok: bool = True, **detail: Any) -> "Trace":
        """Record a completed stage."""

        now = time.time()
        duration = 0.0

        if self._open and self._open[0] == name:
            duration = now - self._open[1]
            self._open = None

        self.steps.append(Step(str(name), now, duration, bool(ok), dict(detail)))

        if not ok and not self.failure_stage:
            self.failure_stage = str(name)

        return self

    def open(self, name: str) -> "Trace":
        """Mark a stage as started so its duration gets measured."""

        self._open = (str(name), time.time())

        return self

    def note_strategy(self, name: str, score: float, reason: str = "") -> "Trace":
        self.strategies_considered.append(
            {"name": name, "score": round(float(score), 4), "reason": reason}
        )

        return self

    def select(self, name: str, reason: str) -> "Trace":
        self.selected_strategy = str(name)
        self.selection_reason = str(reason)

        return self.stage("selection", strategy=name, reason=reason)

    def learn(self, lesson: str) -> "Trace":
        text = str(lesson).strip()

        if text and text not in self.lessons:
            self.lessons.append(text)

        return self

    def finish(
        self,
        status: str,
        verified: bool = False,
        confidence: float = 0.0,
        persist: bool = True,
    ) -> "Trace":
        self.finished = time.time()
        self.status = str(status)
        self.verified = bool(verified)
        self.confidence = round(float(confidence), 4)

        if persist:
            self.save()

        return self

    # ------------------------------------------------------------- readout

    @property
    def duration(self) -> float:
        return (self.finished or time.time()) - self.started

    def stage_names(self) -> list[str]:
        return [s.stage for s in self.steps]

    def covered(self, required: tuple[str, ...]) -> bool:
        """True when every required stage appears, in order."""

        names = self.stage_names()
        position = -1

        for stage in required:
            try:
                position = names.index(stage, position + 1)

            except ValueError:
                return False

        return True

    def report(self) -> dict[str, Any]:
        return {
            "trace_id": self.id,
            "goal": self.goal,
            "status": self.status,
            "verified": self.verified,
            "confidence": self.confidence,
            "started": self.started,
            "finished": self.finished,
            "duration": round(self.duration, 4),
            "stages": [s.report() for s in self.steps],
            "knowledge_used": list(self.knowledge_used),
            "memories_used": list(self.memories_used),
            "hypotheses": list(self.hypotheses),
            "strategies_considered": list(self.strategies_considered),
            "selected_strategy": self.selected_strategy,
            "selection_reason": self.selection_reason,
            "assumptions": list(self.assumptions),
            "lessons": list(self.lessons),
            "failure_stage": self.failure_stage,
        }

    def summary(self) -> str:
        return (
            f"[{self.id}] {self.goal} -> {self.status} "
            f"({len(self.steps)} stages, {self.duration:.2f}s, "
            f"strategy={self.selected_strategy or 'none'})"
        )

    # ------------------------------------------------------------- storage

    def save(self) -> None:
        record = self.report()

        def add(rows: list) -> list:
            rows = [r for r in rows if isinstance(r, dict) and r.get("trace_id") != self.id]
            rows.append(record)

            return rows[-TRACE_LIMIT:]

        with self._lock:
            try:
                self._store.update(add)

            except Exception:
                # A trace failing to persist must never break the task itself.
                pass

    @classmethod
    def recent(cls, limit: int = 20) -> list[dict[str, Any]]:
        rows = [r for r in cls._store.load() if isinstance(r, dict)]

        return rows[-int(limit):][::-1]

    @classmethod
    def load(cls, trace_id: str) -> dict[str, Any] | None:
        for row in cls._store.load():
            if isinstance(row, dict) and row.get("trace_id") == trace_id:
                return row

        return None

    @classmethod
    def metrics(cls) -> dict[str, Any]:
        """Aggregate observability figures (section 80)."""

        rows = [r for r in cls._store.load() if isinstance(r, dict)]

        if not rows:
            return {
                "traces": 0,
                "verified": 0,
                "verification_rate": 0.0,
                "avg_duration": 0.0,
                "failure_stages": {},
                "strategies": {},
            }

        verified = sum(1 for r in rows if r.get("verified"))
        durations = [float(r.get("duration", 0)) for r in rows]
        stages: dict[str, int] = {}
        strategies: dict[str, int] = {}

        for row in rows:
            stage = row.get("failure_stage") or ""

            if stage:
                stages[stage] = stages.get(stage, 0) + 1

            name = row.get("selected_strategy") or ""

            if name:
                strategies[name] = strategies.get(name, 0) + 1

        return {
            "traces": len(rows),
            "verified": verified,
            "verification_rate": round(verified / len(rows), 4),
            "avg_duration": round(sum(durations) / len(durations), 4),
            "failure_stages": stages,
            "strategies": strategies,
        }
