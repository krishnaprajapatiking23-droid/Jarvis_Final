"""Task planning without a model (roadmap sections 1 and 9).

Turns a goal into an ordered, dependency-aware plan of concrete steps, with
verification criteria attached to each one.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List

from brains_v2.ai.reasoning import reasoner

__all__ = ["Planner", "planner", "plan"]

_SPLIT = re.compile(r"\s*(?:,|;|\bthen\b|\band then\b|\bafter that\b|\bnext\b)\s*",
                    re.IGNORECASE)

TEMPLATES = {
    "coding": [
        ("Read the relevant files", "the files were opened"),
        ("Understand the current behaviour", "the behaviour is described"),
        ("Make the change", "the file was written"),
        ("Run the tests", "the test command exited zero"),
        ("Report what changed", "a diff summary exists"),
    ],
    "research": [
        ("Turn the question into search queries", "at least one query exists"),
        ("Collect sources", "two or more sources were fetched"),
        ("Extract and compare evidence", "claims are mapped to sources"),
        ("Resolve contradictions", "no unresolved conflict remains"),
        ("Summarise with citations", "every claim has a source"),
    ],
    "automation": [
        ("Identify the target application or file", "a target was matched"),
        ("Check permissions", "the action is allowed by policy"),
        ("Perform the action", "the action returned a result"),
        ("Verify the new state", "the expected state was observed"),
    ],
    "planning": [
        ("Clarify the goal", "the goal is one sentence"),
        ("Break it into tasks", "at least two tasks exist"),
        ("Order the tasks by dependency", "no cycle remains"),
        ("Attach deadlines", "every task has a due date or none is needed"),
    ],
}

DEFAULT = [
    ("Understand the request", "the goal is stated"),
    ("Decide who should handle it", "a manager was chosen"),
    ("Do the work", "a result exists"),
    ("Verify and report", "the result was checked"),
]


class Planner:
    """Builds an explainable plan from a goal."""

    def explicit_steps(self, text: str) -> List[str]:
        """Steps the user spelled out themselves."""
        parts = [p.strip() for p in _SPLIT.split(str(text or "")) if p.strip()]
        return parts if len(parts) > 1 else []

    def create(self, goal: str) -> Dict[str, Any]:
        analysis = reasoner.analyse(goal)
        explicit = self.explicit_steps(goal)

        if explicit:
            steps = [{"id": index, "action": action,
                      "verify": "the step produced a result",
                      "depends_on": [index - 1] if index > 1 else []}
                     for index, action in enumerate(explicit, start=1)]
        else:
            template = TEMPLATES.get(analysis["domain"], DEFAULT)
            steps = [{"id": index, "action": action, "verify": criterion,
                      "depends_on": [index - 1] if index > 1 else []}
                     for index, (action, criterion) in enumerate(template, start=1)]

        return {
            "goal": analysis["goal"],
            "domain": analysis["domain"],
            "constraints": analysis["constraints"],
            "unknowns": analysis["unknowns"],
            "steps": steps,
            "step_count": len(steps),
        }

    def replan(self, previous: Dict[str, Any], failed_step: int,
               reason: str = "") -> Dict[str, Any]:
        """Rebuild a plan after a step failed (roadmap: Re-Planning After Failure)."""
        steps = [dict(step) for step in previous.get("steps", [])]

        for step in steps:
            if step["id"] == failed_step:
                step["status"] = "failed"
                step["reason"] = reason

        retry = {
            "id": max((s["id"] for s in steps), default=0) + 1,
            "action": "Retry with a different approach: %s"
                      % (reason or "previous attempt failed"),
            "verify": "the retry produced a result",
            "depends_on": [failed_step],
        }
        steps.append(retry)

        replanned = dict(previous)
        replanned["steps"] = steps
        replanned["step_count"] = len(steps)
        replanned["replanned_after"] = failed_step
        return replanned

    def render(self, plan: Dict[str, Any]) -> str:
        lines = ["Goal: %s  (%s)" % (plan.get("goal", ""), plan.get("domain", ""))]
        for step in plan.get("steps", []):
            marker = "x" if step.get("status") == "failed" else " "
            lines.append("  [%s] %d. %s  -- verify: %s"
                         % (marker, step["id"], step["action"], step["verify"]))
        return "\n".join(lines)


planner = Planner()


def plan(goal: str) -> Dict[str, Any]:
    return planner.create(goal)
