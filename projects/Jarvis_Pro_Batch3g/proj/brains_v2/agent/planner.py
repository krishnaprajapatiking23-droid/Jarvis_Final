"""
AI Planner

==========================================
JARVIS PRO - multi-step planning
==========================================

Roadmap section 1 (task decomposition, dynamic planning, re-planning after
failure, plan visualisation) - adapted from Mark-XXXIX-OR ``agent/planner.py``
and wired into the JARVIS tool registry and model router.

Backward compatible: ``planner.plan(goal)`` still returns a list of steps,
so ``brains_v2.agent.agent`` and anything else calling it keeps working.
The richer structure is available through ``planner.create_plan(goal)``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


PLANNER_PROMPT = """You are the planning module of JARVIS, a desktop assistant.

GOAL: {goal}

AVAILABLE CAPABILITIES:
{tools}

Break the goal into the SMALLEST number of concrete steps that actually
achieve it. Reply with JSON only, no prose, no code fences:

{{"steps": [
   {{"action": "what to do, as an imperative sentence",
     "tool": "capability name or empty when it is a reasoning/answering step",
     "arguments": {{}},
     "success": "how to tell this step worked"}}
 ],
 "needs_confirmation": false,
 "notes": "one short sentence"}}

Rules:
- 1 step for simple requests, at most {max_steps} steps.
- Never invent a capability that is not in the list; leave "tool" empty instead.
- Do not write code in the plan.
- Set needs_confirmation to true when a step deletes data, changes system
  settings, or spends money."""


REPLAN_PROMPT = """You are re-planning a failed task for JARVIS.

GOAL: {goal}
COMPLETED STEPS: {done}
FAILED STEP: {failed}
ERROR: {error}

AVAILABLE CAPABILITIES:
{tools}

Produce a NEW plan for the remaining work that avoids the failure.
Use exactly the same JSON format as the planner:
{{"steps": [{{"action": "...", "tool": "", "arguments": {{}}, "success": "..."}}],
  "needs_confirmation": false, "notes": "..."}}"""


@dataclass
class Step:
    action: str
    tool: str = ""
    arguments: dict[str, Any] = field(default_factory=dict)
    success: str = ""

    def __str__(self) -> str:
        return self.action

    def report(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "tool": self.tool,
            "arguments": dict(self.arguments),
            "success": self.success,
        }


@dataclass
class Plan:
    goal: str
    steps: list[Step] = field(default_factory=list)
    needs_confirmation: bool = False
    notes: str = ""
    source: str = "model"

    def __len__(self) -> int:
        return len(self.steps)

    def __iter__(self):
        return iter(self.steps)

    def report(self) -> dict[str, Any]:
        return {
            "goal": self.goal,
            "source": self.source,
            "needs_confirmation": self.needs_confirmation,
            "notes": self.notes,
            "steps": [step.report() for step in self.steps],
        }

    def visualise(self) -> str:
        """Plan visualisation (roadmap section 1)."""

        if not self.steps:
            return "No steps planned."

        lines = [f"Plan for: {self.goal}"]

        for index, step in enumerate(self.steps, start=1):
            tool = f"  [{step.tool}]" if step.tool else ""
            lines.append(f"  {index}. {step.action}{tool}")

        if self.needs_confirmation:
            lines.append("  (needs your confirmation before running)")

        return "\n".join(lines)


# Verbs that clearly mark a multi-part request - used by the offline planner.
SPLIT_PATTERN = re.compile(
    r"\s+(?:and then|then|after that|afterwards|also|;)\s+",
    re.IGNORECASE,
)

RISKY_WORDS = (
    "delete",
    "remove",
    "uninstall",
    "format",
    "shutdown",
    "restart",
    "kill",
    "buy",
    "pay",
    "send money",
)


class AIPlanner:

    # ---------------------------------------------------- helpers

    def _max_steps(self) -> int:
        try:
            from config import config

            return max(int(config.get("agent.max_steps", 8)), 1)

        except Exception:
            return 8

    def _tools(self) -> str:
        try:
            from core.tool_schema import tool_registry

            summary = tool_registry.summary()

            return summary or "- (no tools registered)"

        except Exception:
            return "- (tool registry unavailable)"

    def _parse(self, goal: str, data: Any) -> Plan | None:
        if not isinstance(data, dict):
            return None

        raw_steps = data.get("steps")

        if not isinstance(raw_steps, list) or not raw_steps:
            return None

        steps: list[Step] = []

        for item in raw_steps[: self._max_steps()]:
            if isinstance(item, str):
                action = item.strip()
                tool = ""
                arguments: dict[str, Any] = {}
                success = ""

            elif isinstance(item, dict):
                action = str(
                    item.get("action") or item.get("step") or item.get("task") or ""
                ).strip()
                tool = str(item.get("tool") or "").strip()
                raw_arguments = item.get("arguments")
                arguments = dict(raw_arguments) if isinstance(raw_arguments, dict) else {}
                success = str(item.get("success") or "").strip()

                # the reference planner rejects plans that smuggle in code
                if "generated_code" in item:
                    return None

            else:
                continue

            if action:
                steps.append(Step(action, tool, arguments, success))

        if not steps:
            return None

        return Plan(
            goal=goal,
            steps=steps,
            needs_confirmation=bool(data.get("needs_confirmation"))
            or self._looks_risky(goal),
            notes=str(data.get("notes") or "").strip(),
            source="model",
        )

    def _looks_risky(self, text: str) -> bool:
        lowered = str(text or "").lower()

        return any(word in lowered for word in RISKY_WORDS)

    # ---------------------------------------------------- fallback

    def fallback_plan(self, goal: str) -> Plan:
        """Deterministic offline planner - used when no model answers."""

        goal = str(goal or "").strip()

        parts = [part.strip() for part in SPLIT_PATTERN.split(goal) if part.strip()]

        if len(parts) <= 1:
            parts = [goal] if goal else []

        steps = [Step(action=part) for part in parts[: self._max_steps()]]

        return Plan(
            goal=goal,
            steps=steps,
            needs_confirmation=self._looks_risky(goal),
            notes="Offline plan (no model available).",
            source="fallback",
        )

    # ---------------------------------------------------- planning

    def create_plan(self, goal: str) -> Plan:
        """Full structured plan for a goal."""

        goal = str(goal or "").strip()

        if not goal:
            return Plan(goal="", steps=[], notes="Nothing to plan.", source="empty")

        try:
            from core.model_router import router

            data = router.json(
                PLANNER_PROMPT.format(
                    goal=goal,
                    tools=self._tools(),
                    max_steps=self._max_steps(),
                ),
                capability="chat",
                options={"temperature": 0.2, "num_predict": 700},
            )

            plan = self._parse(goal, data)

            if plan is not None:
                return plan

        except Exception:
            pass

        return self.fallback_plan(goal)

    def replan(
        self,
        goal: str,
        completed: list[Any] | None = None,
        failed_step: Any = "",
        error: str = "",
    ) -> Plan:
        """Build a new plan after a failure (roadmap: re-planning)."""

        try:
            from core.model_router import router

            data = router.json(
                REPLAN_PROMPT.format(
                    goal=goal,
                    done="; ".join(str(item) for item in (completed or [])) or "none",
                    failed=str(failed_step),
                    error=str(error)[:400],
                    tools=self._tools(),
                ),
                capability="chat",
                options={"temperature": 0.2, "num_predict": 700},
            )

            plan = self._parse(goal, data)

            if plan is not None:
                plan.source = "replan"

                return plan

        except Exception:
            pass

        remaining = self.fallback_plan(goal)
        remaining.source = "replan_fallback"

        return remaining

    # ---------------------------------------------------- legacy api

    def plan(self, goal: str) -> list[Step]:
        """Original API: a list of steps.

        Steps stringify to their action text, so old callers that treat the
        list as strings keep working unchanged.
        """

        return list(self.create_plan(goal).steps)


planner = AIPlanner()
