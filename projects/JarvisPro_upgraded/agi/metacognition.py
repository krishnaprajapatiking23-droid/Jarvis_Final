"""
==========================================
JARVIS PRO
AGI metacognition
==========================================

Roadmap sections 39 (self-evaluation), 40 (metacognition), 41 (self-monitoring),
42 (self-reflection), 43 (self-correction) and 44 (self-improvement).

The hard requirement in section 40 is that explanations must correspond to
actual state: "do not generate fake explanations". Every method here derives
its output from the real :class:`~agi.trace.Trace`, the real world model and the
real strategy record. Nothing here composes a plausible-sounding narrative - if
the state does not support a claim, the claim is not made.

    from agi.metacognition import meta

    meta.self_evaluate(trace, goal)      # did I actually satisfy the goal?
    meta.monitor()                       # what is degrading right now?
    meta.reflect(trace, success=False)   # what should change?
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from .goals import Goal
from .strategies import strategies
from .trace import Trace
from .uncertainty import Belief
from .world_model import world

# Repeating the same failing approach this many times triggers a stop.
REPEAT_LIMIT = 2

# Stages whose absence means the loop did not really complete.
ESSENTIAL_STAGES = ("intent", "planning", "execution", "verification")


@dataclass
class Assessment:
    """The result of the system checking its own work."""

    understood_goal: bool
    satisfied_constraints: bool
    plan_complete: bool
    assumptions_supported: bool
    result_verified: bool
    open_questions: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)
    confidence: float = 0.0

    @property
    def passed(self) -> bool:
        return (
            self.understood_goal
            and self.satisfied_constraints
            and self.plan_complete
            and self.result_verified
        )

    def report(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "understood_goal": self.understood_goal,
            "satisfied_constraints": self.satisfied_constraints,
            "plan_complete": self.plan_complete,
            "assumptions_supported": self.assumptions_supported,
            "result_verified": self.result_verified,
            "open_questions": list(self.open_questions),
            "problems": list(self.problems),
            "confidence": round(float(self.confidence), 4),
        }


class Metacognition:
    """Reasoning about the system's own reasoning, grounded in recorded state."""

    def __init__(self) -> None:
        self._attempts: dict[str, list[dict[str, Any]]] = {}

    # ------------------------------------------------------- self-evaluation

    def self_evaluate(
        self,
        trace: Trace,
        goal: Goal | None = None,
        usage: dict[str, Any] | None = None,
    ) -> Assessment:
        """Section 39: check the work against the goal, from recorded state."""

        stages = set(trace.stage_names())
        problems: list[str] = []
        questions: list[str] = []

        understood = "intent" in stages or "goal" in stages

        if not understood:
            problems.append("no intent or goal stage was recorded - the request "
                            "may never have been interpreted")

        # Constraints: checked against the goal's real constraint list.
        satisfied = True

        if goal is not None:
            violations = goal.violations(usage or {})

            if violations:
                satisfied = False
                problems.extend(
                    f"constraint violated: {v['description']}" for v in violations
                )

            for constraint in goal.hard_constraints():
                if constraint.limit is None and usage is not None:
                    if constraint.kind not in usage:
                        questions.append(
                            f"the '{constraint.kind}' constraint was never measured"
                        )

        plan_complete = "planning" in stages and "execution" in stages

        if "planning" in stages and "execution" not in stages:
            problems.append("a plan was made but nothing was executed")

        # Assumptions: real ones, taken from the trace and the world model.
        unsupported = [
            item for item in world.stale() if item["confidence"] < 0.5
        ]
        assumptions_supported = not trace.assumptions and not unsupported

        for assumption in trace.assumptions:
            questions.append(f"unverified assumption carried through: {assumption}")

        for item in unsupported[:3]:
            questions.append(
                f"world model holds '{item['entity']}.{item['property']}' at "
                f"low confidence and has not re-observed it for {int(item['age'])}s"
            )

        verified = trace.verified and "verification" in stages

        if not verified:
            problems.append(
                "the result was not verified" if "verification" not in stages
                else "verification ran but did not confirm the result"
            )

        # Confidence is computed from how many checks actually passed.
        checks = [understood, satisfied, plan_complete, assumptions_supported, verified]
        confidence = round(sum(1 for c in checks if c) / len(checks), 4)

        return Assessment(
            understood_goal=understood,
            satisfied_constraints=satisfied,
            plan_complete=plan_complete,
            assumptions_supported=assumptions_supported,
            result_verified=verified,
            open_questions=questions,
            problems=problems,
            confidence=confidence,
        )

    # ------------------------------------------------------- introspection

    def explain(self, trace: Trace) -> list[str]:
        """Section 40: state *why*, using only what the trace actually holds.

        Each statement is emitted only when the recorded state supports it.
        There is no fallback sentence for "nothing to say" - an empty list is
        the honest answer when the trace carries no explanation.
        """

        statements: list[str] = []

        if trace.failure_stage:
            failed = [s for s in trace.steps if s.stage == trace.failure_stage and not s.ok]
            detail = failed[0].detail if failed else {}
            reason = detail.get("error") or detail.get("reason") or ""

            statements.append(
                f"the {trace.failure_stage} stage failed"
                + (f" because {reason}" if reason else " and recorded no reason")
            )

        if trace.assumptions:
            statements.append(
                "confidence is capped because these assumptions were never "
                "verified: " + "; ".join(trace.assumptions[:3])
            )

        if trace.selected_strategy and trace.selection_reason:
            statements.append(
                f"'{trace.selected_strategy}' was chosen because "
                f"{trace.selection_reason}"
            )

        rejected = [
            s for s in trace.strategies_considered
            if s["name"] != trace.selected_strategy
        ]

        if rejected:
            best_rejected = max(rejected, key=lambda s: s["score"])
            statements.append(
                f"'{best_rejected['name']}' was the closest alternative at "
                f"score {best_rejected['score']}"
            )

        unavailable = [
            s for s in trace.steps
            if s.stage == "selection" and s.detail.get("unavailable")
        ]

        for step in unavailable:
            statements.append(
                f"a tool was unavailable: {step.detail.get('unavailable')}"
            )

        if not trace.verified and trace.status not in ("running",):
            missing = [s for s in ESSENTIAL_STAGES if s not in set(trace.stage_names())]

            if missing:
                statements.append(
                    "the loop is incomplete - these stages never ran: "
                    + ", ".join(missing)
                )

        return statements

    def self_state(self) -> dict[str, Any]:
        """Section 31: what am I doing, with what, and what is uncertain?"""

        try:
            from .capabilities import capabilities
            from .goals import goals

            capability_state = capabilities.status()
            goal_state = goals.status()
            active = goals.active()

        except Exception as exc:
            capability_state = {"error": str(exc)}
            goal_state = {"error": str(exc)}
            active = []

        return {
            "active_goals": [g.description for g in active[:5]],
            "next_action": (
                goals.next_action().description if active and goals.next_action() else None
            ),
            "capabilities": capability_state,
            "goals": goal_state,
            "world": world.status(),
            "strategies": strategies.status(),
            "uncertain": [
                f"{item['entity']}.{item['property']}" for item in world.stale()[:5]
            ],
            "contradictions": world.contradictions()[:5],
        }

    # ------------------------------------------------------- monitoring

    def monitor(self) -> dict[str, Any]:
        """Section 41: what is degrading right now, and what should be done."""

        alerts: list[dict[str, Any]] = []

        failing = strategies.failing()

        for strategy in failing:
            alerts.append(
                {
                    "kind": "failing_strategy",
                    "subject": strategy.name,
                    "detail": (
                        f"{strategy.consecutive_failures} consecutive failures, "
                        f"{strategy.success_rate:.0%} success over "
                        f"{strategy.attempts} attempts"
                    ),
                    "action": "propose a replacement strategy",
                }
            )

        stale = world.stale()

        if len(stale) > 5:
            alerts.append(
                {
                    "kind": "stale_world_model",
                    "subject": f"{len(stale)} facts",
                    "detail": f"oldest is {int(stale[0]['age'])}s out of date",
                    "action": "re-observe before planning against these facts",
                }
            )

        contradictions = world.contradictions()

        if contradictions:
            alerts.append(
                {
                    "kind": "contradiction",
                    "subject": ", ".join(
                        f"{c['entity']}.{c['property']}" for c in contradictions[:3]
                    ),
                    "detail": "evidence points both ways without resolution",
                    "action": "design a discriminating observation",
                }
            )

        metrics = Trace.metrics()

        if metrics["traces"] >= 5 and metrics["verification_rate"] < 0.5:
            alerts.append(
                {
                    "kind": "low_verification_rate",
                    "subject": "overall",
                    "detail": (
                        f"only {metrics['verification_rate']:.0%} of "
                        f"{metrics['traces']} traces verified"
                    ),
                    "action": "review whether verification criteria are checkable",
                }
            )

        if metrics["failure_stages"]:
            worst = max(metrics["failure_stages"].items(), key=lambda kv: kv[1])

            if worst[1] >= 3:
                alerts.append(
                    {
                        "kind": "repeated_stage_failure",
                        "subject": worst[0],
                        "detail": f"{worst[1]} traces failed at this stage",
                        "action": f"investigate the {worst[0]} layer",
                    }
                )

        return {
            "healthy": not alerts,
            "alerts": alerts,
            "metrics": metrics,
            "checked_at": time.time(),
        }

    # ------------------------------------------------------- reflection

    def reflect(
        self,
        trace: Trace,
        success: bool,
        error: str = "",
    ) -> dict[str, Any]:
        """Section 42: what happened, why, and what should change.

        Lessons are only produced where the trace supports them. A run that
        recorded nothing yields no lesson rather than an invented one.
        """

        went_well: list[str] = []
        went_badly: list[str] = []
        lessons: list[str] = []
        changes: list[str] = []

        stages = trace.stage_names()
        ok_stages = [s.stage for s in trace.steps if s.ok]
        bad_stages = [s.stage for s in trace.steps if not s.ok]

        if success:
            if trace.selected_strategy:
                went_well.append(
                    f"'{trace.selected_strategy}' carried the task through "
                    f"{len(ok_stages)} stages"
                )
                lessons.append(
                    f"{trace.selected_strategy} suits problems like: {trace.goal[:100]}"
                )

            if trace.verified:
                went_well.append("the result was verified rather than assumed")

        else:
            if trace.failure_stage:
                went_badly.append(f"failed at the {trace.failure_stage} stage")

                lesson = self._lesson_for_stage(trace, error)

                if lesson:
                    lessons.append(lesson)
                    changes.append(self._change_for_stage(trace.failure_stage))

            if not trace.verified and "verification" not in stages:
                went_badly.append("nothing verified the outcome")
                changes.append("add a checkable verification criterion before executing")

        # Slow stages are a real, measured observation.
        slow = [s for s in trace.steps if s.duration > 5.0]

        if slow:
            went_badly.append(
                f"{len(slow)} stage(s) took over five seconds: "
                + ", ".join(f"{s.stage} ({s.duration:.1f}s)" for s in slow[:3])
            )

        remember = [
            lesson for lesson in lessons
            if len(lesson) > 20 and trace.goal
        ]

        return {
            "trace_id": trace.id,
            "success": bool(success),
            "went_well": went_well,
            "went_badly": went_badly,
            "why": self.explain(trace),
            "lessons": lessons,
            "changes": changes,
            "worth_remembering": bool(remember),
            "reusable": bool(success and trace.selected_strategy and trace.verified),
        }

    def _lesson_for_stage(self, trace: Trace, error: str) -> str:
        """Generalise a failure into a reusable lesson (section 9).

        Turns a concrete failure into a statement about a *class* of
        situation, which is what makes it transferable.
        """

        stage = trace.failure_stage
        detail = error or ""

        generalisations = {
            "execution": "an action can fail even when the plan is sound - verify the "
                         "precondition before executing, not after",
            "verification": "a result that cannot be checked should not be reported as done",
            "planning": "a goal that cannot be decomposed into checkable parts needs "
                        "clarification before planning",
            "selection": "when no capability matches, the gap must be closed or the "
                         "human asked - not worked around silently",
            "safety": "a blocked action means the goal needs a different route, not a retry",
            "observation": "acting on an unobserved environment risks planning against "
                           "state that has already changed",
        }

        base = generalisations.get(stage, "")

        if base and detail:
            return f"{base} (seen here as: {detail[:120]})"

        return base

    def _change_for_stage(self, stage: str) -> str:
        return {
            "execution": "check preconditions as an explicit step before acting",
            "verification": "define the check before the action, not after",
            "planning": "ask for the missing detail before building a plan",
            "selection": "report the capability gap instead of substituting a weaker tool",
            "safety": "route to approval rather than retrying the blocked action",
            "observation": "re-observe the environment at the start of the next attempt",
        }.get(stage, f"review the {stage} stage")

    # ------------------------------------------------------- self-correction

    def record_attempt(
        self, goal: str, approach: str, success: bool, error: str = ""
    ) -> dict[str, Any]:
        """Track attempts so the same failing approach is not repeated."""

        key = str(goal)[:200]
        entry = {
            "approach": str(approach),
            "success": bool(success),
            "error": str(error)[:300],
            "at": time.time(),
        }
        history = self._attempts.setdefault(key, [])
        history.append(entry)
        del history[:-20]

        return entry

    def should_retry(self, goal: str, approach: str) -> dict[str, Any]:
        """Section 43: refuse to repeat an approach that has already failed."""

        history = self._attempts.get(str(goal)[:200], [])
        same = [a for a in history if a["approach"] == str(approach)]
        failures = [a for a in same if not a["success"]]

        if len(failures) >= REPEAT_LIMIT:
            return {
                "retry": False,
                "reason": (
                    f"'{approach}' has already failed {len(failures)} times for "
                    f"this goal - a different approach is required"
                ),
                "previous_errors": [a["error"] for a in failures[-3:] if a["error"]],
                "tried": sorted({a["approach"] for a in history}),
            }

        return {
            "retry": True,
            "attempt_number": len(same) + 1,
            "tried": sorted({a["approach"] for a in history}),
        }

    def diagnose(self, trace: Trace, error: str = "") -> dict[str, Any]:
        """Attribute a failure to a layer and propose the correction."""

        stage = trace.failure_stage or "unknown"

        layer = {
            "intent": "understanding",
            "goal": "understanding",
            "context": "understanding",
            "memory": "retrieval",
            "knowledge": "retrieval",
            "world_model": "world state",
            "planning": "planning",
            "decomposition": "planning",
            "selection": "capability",
            "safety": "policy",
            "execution": "tool",
            "observation": "perception",
            "verification": "verification",
        }.get(stage, "unknown")

        return {
            "failed_stage": stage,
            "failed_layer": layer,
            "error": error,
            "correction": self._change_for_stage(stage),
            "fallback_strategy": (
                strategies.get(trace.selected_strategy).fallback
                if trace.selected_strategy and strategies.get(trace.selected_strategy)
                else ""
            ),
            "evidence": [
                s.report() for s in trace.steps if not s.ok
            ][:3],
        }

    # ------------------------------------------------------- self-improvement

    def propose_improvement(self) -> list[dict[str, Any]]:
        """Section 44: changes with before-state, evidence, test and rollback.

        Only proposals backed by measured evidence are returned.
        """

        proposals: list[dict[str, Any]] = []

        for strategy in strategies.failing():
            proposal = strategies.propose_replacement(strategy.name)

            if not proposal.get("ok"):
                continue

            proposals.append(
                {
                    "target": strategy.name,
                    "kind": "strategy_replacement",
                    "before": {
                        "success_rate": strategy.success_rate,
                        "attempts": strategy.attempts,
                        "consecutive_failures": strategy.consecutive_failures,
                    },
                    "change": f"replace with {proposal['candidate'].name}",
                    "evidence": proposal["evidence"],
                    "test": (
                        "run the replacement on the next three problems matching "
                        "this pattern and compare success rate against the original"
                    ),
                    "rollback": f"strategies.rollback_replacement('{strategy.name}')",
                    "candidate": proposal["candidate"],
                }
            )

        metrics = Trace.metrics()

        for stage, count in metrics.get("failure_stages", {}).items():
            if count < 3:
                continue

            proposals.append(
                {
                    "target": stage,
                    "kind": "stage_hardening",
                    "before": {"failures": count, "traces": metrics["traces"]},
                    "change": self._change_for_stage(stage),
                    "evidence": {
                        "failure_stages": metrics["failure_stages"],
                        "verification_rate": metrics["verification_rate"],
                    },
                    "test": f"measure the {stage} failure count over the next ten traces",
                    "rollback": "revert the stage change; no persistent state is altered",
                }
            )

        return proposals


meta = Metacognition()
