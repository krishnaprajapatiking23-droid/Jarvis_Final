"""
==========================================
JARVIS PRO
AGI goal hierarchy
==========================================

Roadmap sections 34 (goal hierarchy), 35 (multi-objective reasoning),
36 (constraint reasoning), 37 (resource-aware reasoning) and 59 (persistent
goals).

Goals form a tree: MISSION > LONG_TERM > PROJECT > MILESTONE > TASK > SUBTASK >
ACTION. Progress rolls *up* from the leaves, so a milestone cannot report
itself complete while its tasks are open.

Objectives and constraints are separate on purpose. "Finish quickly but do not
break existing functionality" is one goal with two weighted objectives and one
hard constraint - and :meth:`Goal.tradeoff` makes the planner state the
conflict rather than silently optimising one away.

    from agi.goals import goals

    release = goals.create("make the project ready for release", level="PROJECT")
    goals.create("run the test suite", parent=release.id, level="TASK")
    goals.progress()          # rolls up from leaves
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from core.atomic_json import AtomicJSONStore

LEVELS = ("MISSION", "LONG_TERM", "PROJECT", "MILESTONE", "TASK", "SUBTASK", "ACTION")

ACTIVE = "active"
PAUSED = "paused"
COMPLETED = "completed"
ABANDONED = "abandoned"
ARCHIVED = "archived"
BLOCKED = "blocked"

STATUSES = (ACTIVE, PAUSED, COMPLETED, ABANDONED, ARCHIVED, BLOCKED)

# Constraint kinds the planner knows how to check (section 36).
CONSTRAINT_KINDS = (
    "time",
    "memory",
    "cpu",
    "storage",
    "permission",
    "privacy",
    "network",
    "budget",
    "dependency",
    "preference",
    "safety",
)


@dataclass
class Objective:
    """One thing a goal is trying to maximise or minimise."""

    name: str
    weight: float = 1.0
    direction: str = "max"
    measure: str = ""

    def report(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "weight": round(float(self.weight), 3),
            "direction": self.direction,
            "measure": self.measure,
        }


@dataclass
class Constraint:
    """A hard limit a plan must respect."""

    kind: str
    description: str
    limit: Any = None
    hard: bool = True

    def report(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "description": self.description,
            "limit": self.limit,
            "hard": self.hard,
        }

    def violated_by(self, usage: dict[str, Any]) -> bool:
        """True when a measured resource usage breaks this constraint."""

        if self.limit is None:
            return False

        actual = usage.get(self.kind)

        if actual is None:
            return False

        try:
            return float(actual) > float(self.limit)

        except (TypeError, ValueError):
            return False


@dataclass
class Goal:
    description: str
    level: str = "TASK"
    parent: str = ""
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    status: str = ACTIVE
    priority: float = 0.5
    urgency: float = 0.5
    progress: float = 0.0
    deadline: float | None = None
    objectives: list[Objective] = field(default_factory=list)
    constraints: list[Constraint] = field(default_factory=list)
    success_criteria: list[str] = field(default_factory=list)
    depends_on: list[str] = field(default_factory=list)
    confidence: float = 0.5
    created: float = field(default_factory=time.time)
    updated: float = field(default_factory=time.time)
    notes: list[str] = field(default_factory=list)

    # ------------------------------------------------------------- scoring

    def score(self, now: float | None = None) -> float:
        """Ranking score combining priority, urgency and deadline pressure."""

        now = time.time() if now is None else now
        value = 0.6 * float(self.priority) + 0.4 * float(self.urgency)

        if self.deadline:
            remaining = self.deadline - now

            if remaining <= 0:
                value += 0.5

            elif remaining < 3600:
                value += 0.3

            elif remaining < 86400:
                value += 0.15

        if self.status == BLOCKED:
            value -= 0.2

        return round(max(0.0, min(1.5, value)), 4)

    def overdue(self, now: float | None = None) -> bool:
        now = time.time() if now is None else now

        return bool(self.deadline and self.deadline < now and self.status == ACTIVE)

    def tradeoff(self) -> dict[str, Any]:
        """Report competing objectives rather than optimising one away.

        Section 35 requires the planner to *reason over* tradeoffs. Objectives
        pulling in opposite directions are surfaced with their weights so the
        chosen strategy can be justified.
        """

        if len(self.objectives) < 2:
            return {"competing": False, "objectives": [o.report() for o in self.objectives]}

        maximise = [o for o in self.objectives if o.direction == "max"]
        minimise = [o for o in self.objectives if o.direction == "min"]

        # Speed-vs-correctness style tension: two maximised objectives whose
        # weights are close both demand resources from the same budget.
        weights = sorted((o.weight for o in self.objectives), reverse=True)
        close = len(weights) > 1 and abs(weights[0] - weights[1]) < 0.25

        return {
            "competing": bool((maximise and minimise) or close),
            "dominant": max(self.objectives, key=lambda o: o.weight).name,
            "objectives": [o.report() for o in self.objectives],
            "note": (
                "objectives have comparable weight - the plan must state which "
                "it favours and why"
                if close
                else ""
            ),
        }

    def hard_constraints(self) -> list[Constraint]:
        return [c for c in self.constraints if c.hard]

    def violations(self, usage: dict[str, Any]) -> list[dict[str, Any]]:
        return [
            c.report() for c in self.constraints if c.violated_by(usage)
        ]

    # ------------------------------------------------------------- storage

    def report(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "description": self.description,
            "level": self.level,
            "parent": self.parent,
            "status": self.status,
            "priority": round(float(self.priority), 3),
            "urgency": round(float(self.urgency), 3),
            "progress": round(float(self.progress), 3),
            "deadline": self.deadline,
            "objectives": [o.report() for o in self.objectives],
            "constraints": [c.report() for c in self.constraints],
            "success_criteria": list(self.success_criteria),
            "depends_on": list(self.depends_on),
            "confidence": round(float(self.confidence), 3),
            "created": self.created,
            "updated": self.updated,
            "notes": list(self.notes),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Goal":
        goal = cls(
            description=str(data.get("description", "")),
            level=str(data.get("level", "TASK")),
            parent=str(data.get("parent", "")),
            id=str(data.get("id") or uuid.uuid4().hex[:12]),
            status=str(data.get("status", ACTIVE)),
            priority=float(data.get("priority", 0.5)),
            urgency=float(data.get("urgency", 0.5)),
            progress=float(data.get("progress", 0.0)),
            deadline=data.get("deadline"),
            success_criteria=list(data.get("success_criteria") or []),
            depends_on=list(data.get("depends_on") or []),
            confidence=float(data.get("confidence", 0.5)),
            created=float(data.get("created", time.time())),
            updated=float(data.get("updated", time.time())),
            notes=list(data.get("notes") or []),
        )

        for item in data.get("objectives") or []:
            goal.objectives.append(
                Objective(
                    str(item.get("name", "")),
                    float(item.get("weight", 1.0)),
                    str(item.get("direction", "max")),
                    str(item.get("measure", "")),
                )
            )

        for item in data.get("constraints") or []:
            goal.constraints.append(
                Constraint(
                    str(item.get("kind", "dependency")),
                    str(item.get("description", "")),
                    item.get("limit"),
                    bool(item.get("hard", True)),
                )
            )

        return goal


class GoalHierarchy:
    """Persistent tree of goals with roll-up progress."""

    def __init__(self, path: str = "data/agi_goals.json") -> None:
        self._lock = threading.RLock()
        self._store = AtomicJSONStore(path, {})
        self._goals: dict[str, Goal] = {}
        self._loaded = False

    # ------------------------------------------------------------- storage

    def _ensure(self) -> None:
        if self._loaded:
            return

        with self._lock:
            if self._loaded:
                return

            data = self._store.load() or {}

            for item in (data.get("goals") or {}).values():
                try:
                    goal = Goal.from_dict(item)
                    self._goals[goal.id] = goal

                except Exception:
                    continue

            self._loaded = True

    def save(self) -> None:
        self._ensure()

        with self._lock:
            payload = {
                "goals": {k: v.report() for k, v in self._goals.items()},
                "saved": time.time(),
            }

        try:
            self._store.save(payload)

        except Exception:
            pass

    def reload(self) -> "GoalHierarchy":
        with self._lock:
            self._goals.clear()
            self._loaded = False

        self._ensure()

        return self

    # ------------------------------------------------------------- CRUD

    def create(
        self,
        description: str,
        level: str = "TASK",
        parent: str = "",
        priority: float = 0.5,
        urgency: float = 0.5,
        deadline: float | None = None,
        objectives: list[Objective] | None = None,
        constraints: list[Constraint] | None = None,
        success_criteria: list[str] | None = None,
        depends_on: list[str] | None = None,
    ) -> Goal:
        self._ensure()

        if level not in LEVELS:
            raise ValueError(f"unknown goal level: {level}")

        if parent and parent not in self._goals:
            raise KeyError(f"unknown parent goal: {parent}")

        goal = Goal(
            description=str(description).strip(),
            level=level,
            parent=parent,
            priority=priority,
            urgency=urgency,
            deadline=deadline,
            objectives=list(objectives or []),
            constraints=list(constraints or []),
            success_criteria=list(success_criteria or []),
            depends_on=list(depends_on or []),
        )

        if not goal.description:
            raise ValueError("a goal needs a description")

        with self._lock:
            self._goals[goal.id] = goal

        self.save()

        return goal

    def get(self, goal_id: str) -> Goal | None:
        self._ensure()

        return self._goals.get(str(goal_id))

    def children(self, goal_id: str) -> list[Goal]:
        self._ensure()

        with self._lock:
            return [g for g in self._goals.values() if g.parent == goal_id]

    def ancestors(self, goal_id: str) -> list[Goal]:
        self._ensure()
        chain: list[Goal] = []
        current = self.get(goal_id)
        seen: set[str] = set()

        while current and current.parent and current.parent not in seen:
            seen.add(current.parent)
            parent = self.get(current.parent)

            if parent is None:
                break

            chain.append(parent)
            current = parent

        return chain

    def tree(self, root: str = "") -> list[dict[str, Any]]:
        """Nested representation for reporting."""

        def build(goal: Goal) -> dict[str, Any]:
            node = goal.report()
            node["children"] = [build(c) for c in self.children(goal.id)]

            return node

        self._ensure()

        with self._lock:
            roots = [
                g
                for g in self._goals.values()
                if (g.id == root if root else not g.parent)
            ]

        return [build(g) for g in roots]

    def update(self, goal_id: str, **changes: Any) -> Goal | None:
        goal = self.get(goal_id)

        if goal is None:
            return None

        with self._lock:
            for key, value in changes.items():
                if key in ("id", "objectives", "constraints"):
                    continue

                if hasattr(goal, key):
                    setattr(goal, key, value)

            goal.updated = time.time()

        self.save()

        return goal

    def note(self, goal_id: str, text: str) -> Goal | None:
        goal = self.get(goal_id)

        if goal is None:
            return None

        goal.notes.append(f"{time.strftime('%Y-%m-%d %H:%M')} {text}")
        del goal.notes[:-30]
        goal.updated = time.time()
        self.save()

        return goal

    # ------------------------------------------------------------- state

    def set_status(self, goal_id: str, status: str, cascade: bool = True) -> Goal | None:
        if status not in STATUSES:
            raise ValueError(f"unknown status: {status}")

        goal = self.get(goal_id)

        if goal is None:
            return None

        with self._lock:
            goal.status = status
            goal.updated = time.time()

            if status == COMPLETED:
                goal.progress = 1.0

        if cascade and status in (COMPLETED, ABANDONED, ARCHIVED):
            for child in self.children(goal_id):
                if child.status == ACTIVE:
                    self.set_status(child.id, status, cascade=True)

        self._rollup(goal.parent)
        self.save()

        return goal

    def set_progress(self, goal_id: str, value: float) -> Goal | None:
        goal = self.get(goal_id)

        if goal is None:
            return None

        with self._lock:
            goal.progress = max(0.0, min(1.0, float(value)))
            goal.updated = time.time()

            if goal.progress >= 1.0 and goal.status == ACTIVE:
                goal.status = COMPLETED

        self._rollup(goal.parent)
        self.save()

        return goal

    def _rollup(self, goal_id: str) -> None:
        """Recompute a parent's progress from its children, upward."""

        while goal_id:
            goal = self.get(goal_id)

            if goal is None:
                return

            kids = [c for c in self.children(goal.id) if c.status != ABANDONED]

            if kids:
                weighted = sum(
                    c.progress * (2.0 if c.level in ("MILESTONE", "PROJECT") else 1.0)
                    for c in kids
                )
                total = sum(
                    2.0 if c.level in ("MILESTONE", "PROJECT") else 1.0 for c in kids
                )
                goal.progress = round(weighted / total, 4) if total else 0.0

                # A parent may not be complete while a child is still open.
                if goal.progress >= 1.0:
                    if all(c.status in (COMPLETED, ARCHIVED) for c in kids):
                        goal.status = COMPLETED

                    else:
                        goal.progress = 0.99

                elif goal.status == COMPLETED:
                    goal.status = ACTIVE

                goal.updated = time.time()

            goal_id = goal.parent

    def blocked_by(self, goal_id: str) -> list[Goal]:
        """Dependencies that are not yet complete."""

        goal = self.get(goal_id)

        if goal is None:
            return []

        out = []

        for dependency in goal.depends_on:
            other = self.get(dependency)

            if other and other.status not in (COMPLETED, ARCHIVED):
                out.append(other)

        return out

    def ready(self) -> list[Goal]:
        """Active goals whose dependencies are satisfied, best first."""

        self._ensure()

        with self._lock:
            candidates = [g for g in self._goals.values() if g.status == ACTIVE]

        out = [g for g in candidates if not self.blocked_by(g.id)]

        return sorted(out, key=lambda g: g.score(), reverse=True)

    def next_action(self) -> Goal | None:
        """Highest-scoring leaf that can be worked on right now."""

        for goal in self.ready():
            if not self.children(goal.id):
                return goal

        return None

    def active(self, level: str = "") -> list[Goal]:
        self._ensure()

        with self._lock:
            rows = [
                g
                for g in self._goals.values()
                if g.status == ACTIVE and (not level or g.level == level)
            ]

        return sorted(rows, key=lambda g: g.score(), reverse=True)

    def resumable(self) -> list[Goal]:
        """Long-running goals worth picking up again after a restart.

        This *reports* them. Acting on one still requires the authorisation
        path in :mod:`agi.safety` - section 59 forbids autonomous resumption.
        """

        self._ensure()

        with self._lock:
            return sorted(
                [g for g in self._goals.values() if g.status in (ACTIVE, PAUSED)],
                key=lambda g: g.score(),
                reverse=True,
            )

    def overdue(self) -> list[Goal]:
        self._ensure()

        with self._lock:
            return [g for g in self._goals.values() if g.overdue()]

    def status(self) -> dict[str, Any]:
        self._ensure()

        with self._lock:
            rows = list(self._goals.values())

        counts: dict[str, int] = {}

        for goal in rows:
            counts[goal.status] = counts.get(goal.status, 0) + 1

        return {
            "total": len(rows),
            "by_status": counts,
            "by_level": {
                level: sum(1 for g in rows if g.level == level) for level in LEVELS
            },
            "overdue": len(self.overdue()),
            "ready": len(self.ready()),
        }


goals = GoalHierarchy()
