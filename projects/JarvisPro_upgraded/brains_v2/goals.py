"""
==========================================
JARVIS PRO
Goal planner / goal manager
==========================================

Three real defects lived here:

1. ``brains_v2/router_v2.py`` called ``planner.execute(command)`` while this
   class only had ``handle()``.  Every planning route therefore raised
   ``'GoalPlanner' object has no attribute 'execute'`` and the exception was
   printed and swallowed.
2. ``can_handle()`` matched "plan", "goal", "steps", "strategy" and
   "how to" *anywhere* in the message, so ordinary conversation
   ("how to learn Python?", "what is my main goal?") was hijacked by the
   planner instead of being answered.
3. there was no goal *object* at all, so "Create a goal to learn Python,
   then tell me what my current goal is" had nothing to read back.

``execute()`` is now the documented entry point - it validates the request,
builds the plan or runs the goal operation, and returns a structured
result - and ``handle()`` is kept as an alias so older callers keep
working.  Goals are real records (id, title, description, status,
created_at, updated_at, priority) and are kept separate from memories.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

log = logging.getLogger("jarvis.brain.goals")

# "make a plan for ...", "give me a roadmap to ...", "break this into steps"
PLAN_REQUEST = re.compile(
    r"\b(?:"
    r"make|create|build|draw|draft|give|show|write|prepare|outline|plan out"
    r")\b[^.?!]*\b(?:plan|roadmap|strategy|steps|milestones|schedule)\b",
    re.IGNORECASE,
)

PLAN_PREFIX = re.compile(
    r"^(?:please\s+)?(?:jarvis[,\s]+)?"
    r"(?:plan|roadmap|outline)\b",
    re.IGNORECASE,
)

# "Create a goal to learn Python"
GOAL_CREATE = re.compile(
    r"^\s*(?:please\s+)?(?:jarvis[,\s]+)?"
    r"(?:create|add|set|make|start|new)\s+(?:a\s+|an\s+|my\s+|the\s+)?"
    r"(?:new\s+)?goal\s*(?:to|of|for|:|-)?\s*(?P<goal>.+)$",
    re.IGNORECASE,
)

# "What is my current goal?" / "tell me what my current goal is"
GOAL_QUERY = re.compile(
    r"\bmy\s+(?:current\s+|active\s+)?goal\b"
    r"|\bthe\s+(?:current|active)\s+goal\b",
    re.IGNORECASE,
)

# "Mark my goal as done" / "I finished my goal"
GOAL_DONE = re.compile(
    r"\b(?:mark\s+)?(?:my\s+|the\s+)?goal\s+(?:as\s+)?"
    r"(?:done|complete|completed|finished)\b"
    r"|\b(?:completed|finished|achieved)\s+(?:my|the)\s+goal\b",
    re.IGNORECASE,
)

# "Delete my goal" / "clear the goal"
GOAL_DROP = re.compile(
    r"^\s*(?:please\s+)?(?:delete|remove|clear|cancel|drop|forget)\s+"
    r"(?:my\s+|the\s+)?goals?\b",
    re.IGNORECASE,
)

# Questions are answered by the conversation system, not the planner.
QUESTION_STARTERS = (
    "what", "who", "when", "where", "why", "how", "which", "whose",
    "is", "are", "was", "were", "do", "does", "did", "can", "could",
    "tell", "explain", "remind",
)

JARVIS_STEPS = [
    "Analyze request",
    "Design solution",
    "Write code",
    "Test code",
    "Verify output",
]


def _is_question(command: str) -> bool:
    text = (command or "").strip().lower()

    if not text:
        return False

    if text.endswith("?"):
        return True

    first = text.split()[0].strip(",.!")

    return first in QUESTION_STARTERS


def _clean_goal(text: str) -> str:
    """Drop a trailing follow-up clause from a goal title.

    "learn Python, then tell me what my current goal is"
        -> "learn Python"
    """

    goal = (text or "").strip().strip(".!")

    goal = re.split(
        r",?\s*(?:and\s+then|then|after\s+that|also)\b",
        goal,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]

    return " ".join(goal.split()).strip(" ,.;:-")


class GoalPlanner:
    """Keeps the current goal, its steps, and the goal records."""

    def __init__(self) -> None:
        self.current_goal: Optional[str] = None
        self.tasks: List[str] = []
        self.goals: List[Dict[str, Any]] = []

    # ------------------------------------------------------------------
    def create(self, goal: str) -> Dict[str, Any]:
        """Set ``goal`` as the active goal and derive its steps."""

        text = _clean_goal(goal)

        if not text:
            return self.current()

        now = datetime.now().isoformat(timespec="seconds")

        self.current_goal = text
        self.tasks = list(JARVIS_STEPS) if "jarvis" in text.lower() else [
            "Complete request"
        ]

        self.goals.append(
            {
                "id": len(self.goals) + 1,
                "title": text,
                "description": text,
                "status": "active",
                "created_at": now,
                "updated_at": now,
                "priority": "normal",
            }
        )

        log.info("[GOAL] created %r", text)

        return self.current()

    # ------------------------------------------------------------------
    def current(self) -> Dict[str, Any]:
        return {
            "goal": self.current_goal,
            "tasks": list(self.tasks),
            "record": dict(self.goals[-1]) if self.goals else None,
        }

    # ------------------------------------------------------------------
    def complete(self) -> Dict[str, Any]:
        """Mark the active goal as done."""

        if self.goals:
            self.goals[-1]["status"] = "done"
            self.goals[-1]["updated_at"] = datetime.now().isoformat(
                timespec="seconds"
            )

        done = self.current_goal
        self.current_goal = None
        self.tasks = []

        log.info("[GOAL] completed %r", done)

        return {"goal": done, "tasks": [], "record": None}

    # ------------------------------------------------------------------
    def clear(self) -> Dict[str, Any]:
        """Delete the active goal."""

        if self.goals:
            self.goals[-1]["status"] = "deleted"
            self.goals[-1]["updated_at"] = datetime.now().isoformat(
                timespec="seconds"
            )

        self.current_goal = None
        self.tasks = []

        return self.current()

    # ------------------------------------------------------------------
    def can_handle(self, command: str) -> bool:
        """True only for an explicit planning or goal request.

        "Make me a plan for learning Python"      -> True
        "Create a goal to learn Python"           -> True
        "What is the main goal we discussed?"     -> False
        "How to learn Python?"                    -> False
        """

        text = (command or "").strip()

        if not text:
            return False

        if GOAL_CREATE.match(text) or GOAL_DONE.search(text) or GOAL_DROP.match(text):
            return True

        if GOAL_QUERY.search(text):
            return True

        if _is_question(text):
            return False

        return bool(PLAN_REQUEST.search(text) or PLAN_PREFIX.match(text))

    # ------------------------------------------------------------------
    def _goal_reply(self) -> str:
        """Natural sentence describing the active goal."""

        if not self.current_goal:
            return "You don't have an active goal right now."

        return f"Your current goal is to {self.current_goal}."

    # ------------------------------------------------------------------
    def execute(self, command: str) -> Dict[str, Any]:
        """Router entry point: run the goal operation or build a plan.

        Returns ``{"handled": bool, "reply": str, "goal": ..., "tasks": [...]}``.
        ``handled`` is False when the planner should not answer, which lets
        the router fall through to the conversation system instead of
        producing an empty planner reply.
        """

        text = (command or "").strip()

        if not self.can_handle(text):
            log.debug("planner declined %r", command)
            return {"handled": False, "reply": "", **self.current()}

        # ---------- delete ----------
        if GOAL_DROP.match(text):
            self.clear()

            return {
                "handled": True,
                "reply": "Done - that goal is cleared.",
                **self.current(),
            }

        # ---------- complete ----------
        if GOAL_DONE.search(text):
            done = self.complete()

            reply = (
                f"Nice - \"{done['goal']}\" is marked as done."
                if done["goal"]
                else "There was no active goal to complete."
            )

            return {"handled": True, "reply": reply, **self.current()}

        # ---------- create (may be followed by a query) ----------
        created = GOAL_CREATE.match(text)

        if created:
            self.create(created.group("goal"))

            reply = f"Goal set: {self.current_goal}."

            if GOAL_QUERY.search(text):
                reply = f"{reply} {self._goal_reply()}"

            return {"handled": True, "reply": reply, **self.current()}

        # ---------- query ----------
        if GOAL_QUERY.search(text):
            return {
                "handled": True,
                "reply": self._goal_reply(),
                **self.current(),
            }

        # ---------- plan ----------
        plan = self.create(text)

        log.info("planner built %s step(s) for %r", len(plan["tasks"]), command)

        return {"handled": True, "reply": "", **plan}

    # ------------------------------------------------------------------
    def handle(self, command: str) -> Dict[str, Any]:
        """Backwards-compatible alias for :meth:`execute`."""

        return self.execute(command)


planner = GoalPlanner()

__all__ = ["GoalPlanner", "planner"]
