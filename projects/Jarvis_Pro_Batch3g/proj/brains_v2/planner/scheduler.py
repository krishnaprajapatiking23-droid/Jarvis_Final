"""Canonical plan scheduler (BUG 1).

This module owns the real implementation. The legacy misspelled module is a
thin re-export wrapper, so deleting it cannot break anything here.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional

__all__ = [
    "StepState",
    "ScheduledStep",
    "Schedule",
    "PlanScheduler",
    "build_schedule",
    "scheduler",
    "MAX_STEPS",
]

log = logging.getLogger(__name__)

MAX_STEPS = 200


class StepState:
    """Lifecycle states of a scheduled step."""

    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class ScheduledStep:
    """A single unit of work in a plan."""

    name: str
    action: str = ""
    arguments: Dict[str, Any] = field(default_factory=dict)
    depends_on: List[str] = field(default_factory=list)
    state: str = StepState.PENDING
    result: Any = None
    error: str = ""

    @property
    def finished(self) -> bool:
        return self.state in (StepState.DONE, StepState.FAILED, StepState.SKIPPED)


@dataclass
class Schedule:
    """An ordered, dependency-resolved list of steps."""

    steps: List[ScheduledStep] = field(default_factory=list)
    cycles: List[str] = field(default_factory=list)

    @property
    def order(self) -> List[str]:
        return [step.name for step in self.steps]

    def get(self, name: str) -> Optional[ScheduledStep]:
        for step in self.steps:
            if step.name == name:
                return step
        return None

    def report(self) -> Dict[str, Any]:
        return {
            "order": self.order,
            "cycles": list(self.cycles),
            "states": {step.name: step.state for step in self.steps},
        }


def _as_step(item: Any, index: int) -> ScheduledStep:
    """Accept dicts, ScheduledStep instances or plain strings."""
    if isinstance(item, ScheduledStep):
        return item
    if isinstance(item, dict):
        name = str(item.get("name") or item.get("id") or f"step_{index}")
        depends = item.get("depends_on") or item.get("after") or []
        if isinstance(depends, str):
            depends = [depends]
        return ScheduledStep(
            name=name,
            action=str(item.get("action") or item.get("tool") or ""),
            arguments=dict(item.get("arguments") or item.get("args") or {}),
            depends_on=[str(value) for value in depends],
        )
    return ScheduledStep(name=str(item), action=str(item))


def build_schedule(steps: Iterable[Any]) -> Schedule:
    """Topologically order ``steps``; cycles are reported, never looped over."""
    parsed = [_as_step(item, index) for index, item in enumerate(steps)]
    if len(parsed) > MAX_STEPS:
        raise ValueError(f"plan exceeds {MAX_STEPS} steps")

    remaining = {step.name: step for step in parsed}
    ordered: List[ScheduledStep] = []
    satisfied: set = set()

    while remaining:
        ready = [
            step
            for step in remaining.values()
            if all(dep in satisfied or dep not in remaining for dep in step.depends_on)
        ]
        if not ready:
            cycles = sorted(remaining)
            log.warning("unresolvable plan dependencies: %s", cycles)
            return Schedule(steps=ordered, cycles=cycles)
        for step in ready:
            ordered.append(step)
            satisfied.add(step.name)
            remaining.pop(step.name, None)

    return Schedule(steps=ordered)


class PlanScheduler:
    """Runs a schedule step by step with explicit failure handling."""

    def __init__(self, executor: Optional[Callable[[ScheduledStep], Any]] = None):
        self.executor = executor

    def schedule(self, steps: Iterable[Any]) -> Schedule:
        return build_schedule(steps)

    def _skip_dependents(self, schedule: Schedule, failed: str) -> None:
        blocked = {failed}
        for step in schedule.steps:
            if step.state != StepState.PENDING:
                continue
            if any(dep in blocked for dep in step.depends_on):
                step.state = StepState.SKIPPED
                step.error = f"skipped because '{failed}' failed"
                blocked.add(step.name)

    def run(
        self,
        steps: Iterable[Any],
        executor: Optional[Callable[[ScheduledStep], Any]] = None,
        stop_on_error: bool = True,
    ) -> Dict[str, Any]:
        """Execute a plan. Returns counts plus the per-step report."""
        runner = executor or self.executor
        schedule = self.schedule(steps)
        done = 0
        failed = 0

        for step in schedule.steps:
            if step.state != StepState.PENDING:
                continue
            if runner is None:
                step.state = StepState.SKIPPED
                step.error = "no executor configured"
                continue
            step.state = StepState.RUNNING
            try:
                step.result = runner(step)
                step.state = StepState.DONE
                done += 1
            except Exception as error:
                step.state = StepState.FAILED
                step.error = f"{type(error).__name__}: {error}"
                failed += 1
                log.warning("step '%s' failed: %s", step.name, step.error)
                self._skip_dependents(schedule, step.name)
                if stop_on_error:
                    break

        return {
            "ok": failed == 0 and not schedule.cycles,
            "done": done,
            "failed": failed,
            "total": len(schedule.steps),
            "schedule": schedule.report(),
        }


scheduler = PlanScheduler()
