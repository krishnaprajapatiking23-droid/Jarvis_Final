"""Agent base class (roadmap section 18).

An agent owns a goal: it plans, executes step by step, verifies each step and
re-plans on failure, with a hard bound on iterations so it can never loop
forever.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Callable, Dict, List, Optional

__all__ = ["Agent", "AgentResult", "MAX_STEPS"]

log = logging.getLogger("jarvis.agents")

MAX_STEPS = 12
MAX_SECONDS = 120.0


def AgentResult(success: bool, reply: str = "", **extra: Any) -> Dict[str, Any]:
    result: Dict[str, Any] = {"success": bool(success), "reply": reply}
    result.update(extra)
    return result


class Agent:
    """Bounded goal-directed worker."""

    name = "agent"
    description = ""
    capability = "generic"

    def can_handle(self, goal: str) -> bool:
        return False

    def plan(self, goal: str) -> List[Dict[str, Any]]:
        from brains_v2.ai.planner import planner

        return planner.create(goal)["steps"]

    def act(self, step: Dict[str, Any], goal: str,
            context: Dict[str, Any]) -> Dict[str, Any]:
        """Perform one step. Subclasses override this."""
        return AgentResult(False, "%s cannot perform %r"
                           % (self.name, step.get("action")))

    def verify(self, step: Dict[str, Any], outcome: Dict[str, Any]) -> bool:
        return bool(outcome.get("success"))

    def run(self, goal: str, max_steps: int = MAX_STEPS,
            on_progress: Optional[Callable[[Dict[str, Any]], None]] = None
            ) -> Dict[str, Any]:
        """Execute the plan with bounded retries and a wall-clock limit."""
        started = time.time()
        steps = self.plan(goal)
        context: Dict[str, Any] = {"goal": goal, "results": []}
        history: List[Dict[str, Any]] = []
        replans = 0

        index = 0
        while index < len(steps) and index < max_steps:
            if time.time() - started > MAX_SECONDS:
                return AgentResult(False, "%s ran out of time." % self.name,
                                   history=history, timed_out=True)

            step = steps[index]
            try:
                outcome = self.act(step, goal, context)
            except Exception as error:
                log.warning("%s step %s raised: %r", self.name, step.get("id"), error)
                outcome = AgentResult(False, "%s: %s" % (type(error).__name__, error))

            verified = self.verify(step, outcome)
            record = {"step": step.get("id", index + 1),
                      "action": step.get("action", ""),
                      "success": verified,
                      "reply": outcome.get("reply", "")}
            history.append(record)
            context["results"].append(outcome)

            if on_progress:
                try:
                    on_progress(record)
                except Exception:
                    pass

            if not verified:
                if replans >= 2:
                    return AgentResult(
                        False,
                        "%s could not complete the goal: %s"
                        % (self.name, outcome.get("reply", "step failed")),
                        history=history, replans=replans)
                from brains_v2.ai.planner import planner

                replans += 1
                steps = planner.replan({"steps": steps}, step.get("id", index + 1),
                                       outcome.get("reply", ""))["steps"]
                index += 1
                continue

            index += 1

        return AgentResult(True, self.summarise(history), history=history,
                           replans=replans,
                           seconds=round(time.time() - started, 2))

    def summarise(self, history: List[Dict[str, Any]]) -> str:
        done = sum(1 for record in history if record["success"])
        return "%s finished %d of %d step(s)." % (self.name, done, len(history))

    def health(self) -> Dict[str, Any]:
        return {"available": True, "capability": self.capability, "detail": ""}
