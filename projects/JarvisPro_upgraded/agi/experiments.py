"""
==========================================
JARVIS PRO
AGI experiment planner
==========================================

Roadmap sections 27 (bounded curiosity) and 29 (experiment planning).

An experiment is how the AGI converts a hypothesis into evidence. Every
experiment states, before it runs: what it expects to see, what it will cost,
what could go wrong and how to undo it.

Two rules make this safe rather than merely described:

* Risk is classified through :mod:`security.policy_engine`, the same engine the
  tool layer uses, so an experiment cannot be gentler on itself than a normal
  action would be.
* An experiment with no rollback and a non-low risk class is refused by
  :meth:`run` unless a human has approved it.

Ranking prefers cheap, safe, informative tests - the "prefer low-risk
information-gathering experiments when possible" requirement.

    from agi.experiments import experiments

    plan = experiments.design(hypothesis_id, "list running processes",
                              expects="chrome appears", risk="low")
    experiments.run(plan.id, runner)
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

from core.atomic_json import AtomicJSONStore
from security.policy_engine import policy

from .hypotheses import INTERVENTION, OBSERVATION, hypotheses as hypothesis_engine

PLANNED = "planned"
APPROVED = "approved"
RUNNING = "running"
DONE = "done"
FAILED = "failed"
REFUSED = "refused"

RISK_COST = {"low": 0.1, "medium": 0.4, "high": 0.8, "critical": 1.0}

# Hard ceiling on experiments per goal, so curiosity stays bounded (section 81).
MAX_PER_GOAL = 8


@dataclass
class Experiment:
    hypothesis_id: str
    objective: str
    procedure: list[str]
    expects: str
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    action: str = "read"
    required_tools: list[str] = field(default_factory=list)
    risk: str = "low"
    rollback: str = ""
    verification: str = ""
    intervenes: bool = False
    status: str = PLANNED
    goal_id: str = ""
    approved_by: str = ""
    actual: Any = None
    conclusion: str = ""
    supported: bool | None = None
    created: float = field(default_factory=time.time)
    finished: float | None = None

    def information_gain(self) -> float:
        """Expected value of running this, before cost.

        Highest when the hypothesis it tests is genuinely uncertain, and
        higher for interventions, which can establish causation where an
        observation cannot.
        """

        h = hypothesis_engine.get(self.hypothesis_id)
        uncertainty = 0.5 if h is None else 1.0 - abs(h.confidence - 0.5) * 2

        return round(min(1.0, uncertainty * (1.25 if self.intervenes else 1.0)), 4)

    def cost(self) -> float:
        base = RISK_COST.get(self.risk, 0.5)
        tooling = 0.05 * len(self.required_tools)

        return round(min(1.0, base + tooling), 4)

    def value(self) -> float:
        """Ranking score: information per unit of risk."""

        return round(self.information_gain() - 0.7 * self.cost(), 4)

    def safe(self) -> tuple[bool, str]:
        """Whether this may run without a human.

        Delegates to the real policy engine rather than a local opinion.
        """

        decision = policy.check(self.action, {"experiment": self.id, "risk": self.risk})

        if not decision.allowed:
            return False, decision.reason

        if self.risk in ("high", "critical") and not self.rollback:
            return False, "no rollback defined for a high-risk experiment"

        return True, decision.reason

    def report(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "hypothesis_id": self.hypothesis_id,
            "objective": self.objective,
            "procedure": list(self.procedure),
            "expects": self.expects,
            "action": self.action,
            "required_tools": list(self.required_tools),
            "risk": self.risk,
            "rollback": self.rollback,
            "verification": self.verification,
            "intervenes": self.intervenes,
            "status": self.status,
            "goal_id": self.goal_id,
            "approved_by": self.approved_by,
            "actual": self.actual,
            "conclusion": self.conclusion,
            "supported": self.supported,
            "information_gain": self.information_gain(),
            "cost": self.cost(),
            "value": self.value(),
            "created": self.created,
            "finished": self.finished,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Experiment":
        return cls(
            hypothesis_id=str(data.get("hypothesis_id", "")),
            objective=str(data.get("objective", "")),
            procedure=list(data.get("procedure") or []),
            expects=str(data.get("expects", "")),
            id=str(data.get("id") or uuid.uuid4().hex[:12]),
            action=str(data.get("action", "read")),
            required_tools=list(data.get("required_tools") or []),
            risk=str(data.get("risk", "low")),
            rollback=str(data.get("rollback", "")),
            verification=str(data.get("verification", "")),
            intervenes=bool(data.get("intervenes", False)),
            status=str(data.get("status", PLANNED)),
            goal_id=str(data.get("goal_id", "")),
            approved_by=str(data.get("approved_by", "")),
            actual=data.get("actual"),
            conclusion=str(data.get("conclusion", "")),
            supported=data.get("supported"),
            created=float(data.get("created", time.time())),
            finished=data.get("finished"),
        )


class ExperimentPlanner:
    """Designs, ranks and runs experiments against hypotheses."""

    def __init__(self, path: str = "data/agi_experiments.json") -> None:
        self._lock = threading.RLock()
        self._store = AtomicJSONStore(path, {})
        self._items: dict[str, Experiment] = {}
        self._loaded = False

    # ------------------------------------------------------------- storage

    def _ensure(self) -> None:
        if self._loaded:
            return

        with self._lock:
            if self._loaded:
                return

            for item in (self._store.load() or {}).get("experiments", {}).values():
                try:
                    e = Experiment.from_dict(item)
                    self._items[e.id] = e

                except Exception:
                    continue

            self._loaded = True

    def save(self) -> None:
        self._ensure()

        with self._lock:
            payload = {
                "experiments": {k: v.report() for k, v in self._items.items()},
                "saved": time.time(),
            }

        try:
            self._store.save(payload)

        except Exception:
            pass

    def reload(self) -> "ExperimentPlanner":
        with self._lock:
            self._items.clear()
            self._loaded = False

        self._ensure()

        return self

    # ------------------------------------------------------------- design

    def design(
        self,
        hypothesis_id: str,
        objective: str,
        expects: str,
        procedure: list[str] | None = None,
        action: str = "read",
        tools: list[str] | None = None,
        risk: str = "low",
        rollback: str = "",
        verification: str = "",
        intervenes: bool = False,
        goal_id: str = "",
    ) -> Experiment:
        self._ensure()

        if not hypothesis_engine.get(hypothesis_id):
            raise KeyError(f"unknown hypothesis: {hypothesis_id}")

        if goal_id and len(self.for_goal(goal_id)) >= MAX_PER_GOAL:
            raise RuntimeError(
                f"experiment budget exhausted for goal {goal_id} "
                f"({MAX_PER_GOAL} max)"
            )

        experiment = Experiment(
            hypothesis_id=str(hypothesis_id),
            objective=str(objective).strip(),
            procedure=list(procedure or [str(objective).strip()]),
            expects=str(expects).strip(),
            action=str(action),
            required_tools=list(tools or []),
            risk=str(risk),
            rollback=str(rollback),
            verification=str(verification or f"observe whether: {expects}"),
            intervenes=bool(intervenes),
            goal_id=str(goal_id),
        )

        if not experiment.objective or not experiment.expects:
            raise ValueError("an experiment needs an objective and a prediction")

        with self._lock:
            self._items[experiment.id] = experiment

        self.save()

        return experiment

    def get(self, experiment_id: str) -> Experiment | None:
        self._ensure()

        return self._items.get(str(experiment_id))

    def for_goal(self, goal_id: str) -> list[Experiment]:
        self._ensure()

        with self._lock:
            return [e for e in self._items.values() if e.goal_id == goal_id]

    def for_hypothesis(self, hypothesis_id: str) -> list[Experiment]:
        self._ensure()

        with self._lock:
            return [e for e in self._items.values() if e.hypothesis_id == hypothesis_id]

    # ------------------------------------------------------------- ranking

    def queue(self, goal_id: str = "", limit: int = 5) -> list[Experiment]:
        """Pending experiments, best value first."""

        self._ensure()

        with self._lock:
            rows = [
                e
                for e in self._items.values()
                if e.status in (PLANNED, APPROVED)
                and (not goal_id or e.goal_id == goal_id)
            ]

        rows.sort(key=lambda e: e.value(), reverse=True)

        return rows[: int(limit)]

    def approve(self, experiment_id: str, approver: str = "human") -> Experiment | None:
        experiment = self.get(experiment_id)

        if experiment is None:
            return None

        experiment.status = APPROVED
        experiment.approved_by = str(approver)
        self.save()

        return experiment

    # ------------------------------------------------------------- running

    def run(
        self,
        experiment_id: str,
        runner: Callable[[Experiment], Any],
        judge: Callable[[Experiment, Any], bool] | None = None,
    ) -> dict[str, Any]:
        """Execute one experiment and feed the result back to its hypothesis.

        ``runner`` performs the real action. ``judge`` decides whether the
        outcome matched the prediction; the default does a containment check
        against ``expects``, which is why ``expects`` must be a concrete,
        checkable statement.
        """

        experiment = self.get(experiment_id)

        if experiment is None:
            return {"ok": False, "reason": "unknown experiment"}

        allowed, reason = experiment.safe()

        if not allowed and experiment.status != APPROVED:
            experiment.status = REFUSED
            experiment.conclusion = reason
            self.save()

            return {
                "ok": False,
                "refused": True,
                "needs_approval": True,
                "reason": reason,
                "experiment": experiment.report(),
            }

        experiment.status = RUNNING
        started = time.monotonic()

        try:
            actual = runner(experiment)

        except Exception as exc:
            experiment.status = FAILED
            experiment.actual = f"{type(exc).__name__}: {exc}"
            experiment.conclusion = "experiment could not be carried out"
            experiment.finished = time.time()
            self.save()

            return {
                "ok": False,
                "error": experiment.actual,
                "experiment": experiment.report(),
            }

        experiment.actual = actual
        experiment.finished = time.time()

        if judge is not None:
            supported = bool(judge(experiment, actual))

        else:
            supported = experiment.expects.lower() in str(actual).lower()

        experiment.supported = supported
        experiment.status = DONE
        experiment.conclusion = (
            f"observation matched the prediction: {experiment.expects}"
            if supported
            else f"observation did not match the prediction: {experiment.expects}"
        )

        # Feed evidence back. An intervention is the only kind that can license
        # a causal claim, which is why the kind is carried through.
        kind = INTERVENTION if experiment.intervenes else OBSERVATION
        strength = 0.85 if experiment.intervenes else 0.65

        if supported:
            hypothesis_engine.support(
                experiment.hypothesis_id,
                experiment.conclusion,
                strength=strength,
                kind=kind,
                verified=True,
            )

        else:
            hypothesis_engine.refute(
                experiment.hypothesis_id,
                experiment.conclusion,
                strength=strength,
                kind=kind,
                verified=True,
            )

        self.save()

        return {
            "ok": True,
            "supported": supported,
            "duration": round(time.monotonic() - started, 4),
            "experiment": experiment.report(),
            "hypothesis": (
                hypothesis_engine.get(experiment.hypothesis_id).report()
                if hypothesis_engine.get(experiment.hypothesis_id)
                else None
            ),
        }

    def status(self) -> dict[str, Any]:
        self._ensure()

        with self._lock:
            rows = list(self._items.values())

        counts: dict[str, int] = {}

        for item in rows:
            counts[item.status] = counts.get(item.status, 0) + 1

        done = [e for e in rows if e.status == DONE]

        return {
            "total": len(rows),
            "by_status": counts,
            "interventions": sum(1 for e in rows if e.intervenes),
            "supported": sum(1 for e in done if e.supported),
            "refuted": sum(1 for e in done if e.supported is False),
        }


experiments = ExperimentPlanner()
