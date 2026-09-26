"""
Unified Task Object, State Machine, Execution Context,
Task Handoff, and Cancellation Propagation
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4


VALID_STATES = {
    "pending",
    "running",
    "completed",
    "failed",
    "cancelled",
    "replanned",
    "handed_off",
}


VALID_TRANSITIONS = {
    "pending": {"running", "cancelled", "handed_off"},
    "running": {"completed", "failed", "cancelled", "handed_off"},
    "failed": {"replanned", "cancelled", "handed_off"},
    "replanned": {"running", "cancelled", "handed_off"},
    "handed_off": {"running", "cancelled"},
    "completed": set(),
    "cancelled": set(),
}


@dataclass
class ExecutionContext:

    working_directory: str | None = None
    active_manager: str | None = None
    current_step: int | None = None
    variables: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def set_variable(
        self,
        name: str,
        value: Any,
    ) -> None:
        self.variables[name] = value

    def get_variable(
        self,
        name: str,
        default: Any = None,
    ) -> Any:
        return self.variables.get(name, default)

    def set_metadata(
        self,
        name: str,
        value: Any,
    ) -> None:
        self.metadata[name] = value

    def to_dict(self) -> dict[str, Any]:
        return {
            "working_directory": self.working_directory,
            "active_manager": self.active_manager,
            "current_step": self.current_step,
            "variables": dict(self.variables),
            "metadata": dict(self.metadata),
        }


@dataclass
class Task:

    goal: str
    steps: list[Any] = field(default_factory=list)
    priority: int = 5
    confidence: int = 0
    status: str = "pending"
    context: dict[str, Any] = field(default_factory=dict)
    result: Any = None
    error: str | None = None
    task_id: str = field(
        default_factory=lambda: str(uuid4())
    )
    assigned_manager: str | None = None
    handoff_history: list[dict[str, Any]] = field(
        default_factory=list
    )
    execution_context: ExecutionContext = field(
        default_factory=ExecutionContext
    )
    parent_task_id: str | None = None
    child_task_ids: list[str] = field(
        default_factory=list
    )

    def transition(
        self,
        new_status: str,
    ) -> None:

        if new_status not in VALID_STATES:
            raise ValueError(
                f"Invalid task state: {new_status}"
            )

        allowed = VALID_TRANSITIONS[self.status]

        if new_status not in allowed:
            raise ValueError(
                f"Cannot transition from "
                f"{self.status} to {new_status}"
            )

        self.status = new_status

    def start(self) -> None:

        self.transition("running")
        self.error = None

    def complete(
        self,
        result: Any = None,
    ) -> None:

        self.transition("completed")
        self.result = result
        self.error = None

    def fail(
        self,
        error: str,
    ) -> None:

        self.transition("failed")
        self.error = error

    def replan(self) -> None:

        self.transition("replanned")

    def cancel(self) -> None:

        self.transition("cancelled")

    def handoff(
        self,
        target_manager: str,
        reason: str | None = None,
    ) -> dict[str, Any]:

        previous_manager = self.assigned_manager

        self.transition("handed_off")

        self.assigned_manager = target_manager

        handoff = {
            "task_id": self.task_id,
            "from_manager": previous_manager,
            "to_manager": target_manager,
            "reason": reason,
        }

        self.handoff_history.append(handoff)

        self.execution_context.active_manager = (
            target_manager
        )

        return dict(handoff)

    def add_child(
        self,
        child_task: "Task",
    ) -> None:

        child_task.parent_task_id = self.task_id

        if child_task.task_id not in self.child_task_ids:
            self.child_task_ids.append(
                child_task.task_id
            )

    def is_finished(self) -> bool:

        return self.status in {
            "completed",
            "cancelled",
        }

    def is_failed(self) -> bool:

        return self.status == "failed"

    def to_dict(self) -> dict[str, Any]:

        return {
            "task_id": self.task_id,
            "goal": self.goal,
            "steps": list(self.steps),
            "priority": self.priority,
            "confidence": self.confidence,
            "status": self.status,
            "context": dict(self.context),
            "result": self.result,
            "error": self.error,
            "assigned_manager": self.assigned_manager,
            "handoff_history": list(
                self.handoff_history
            ),
            "parent_task_id": self.parent_task_id,
            "child_task_ids": list(
                self.child_task_ids
            ),
            "execution_context": (
                self.execution_context.to_dict()
            ),
        }


class TaskEngine:

    def __init__(self):

        self.tasks: list[Task] = []

    def add(
        self,
        task: Task,
    ) -> Task:

        self.tasks.append(task)

        return task

    def next(self) -> Task | None:

        for task in self.tasks:

            if task.status == "pending":
                return task

        return None

    def get_task(
        self,
        task_id: str,
    ) -> Task | None:

        for task in self.tasks:

            if task.task_id == task_id:
                return task

        return None

    def add_child_task(
        self,
        parent: Task,
        child: Task,
    ) -> Task:

        parent.add_child(child)
        self.add(child)

        return child

    def cancel_task(
        self,
        task_id: str,
        reason: str = "Parent task cancelled",
    ) -> list[str]:

        task = self.get_task(task_id)

        if task is None:
            return []

        cancelled_ids: list[str] = []

        def cancel_recursive(
            current: Task,
        ) -> None:

            if current.status not in {
                "completed",
                "cancelled",
            }:

                current.error = reason

                if current.status != "cancelled":
                    current.transition("cancelled")

                cancelled_ids.append(
                    current.task_id
                )

            for child_id in current.child_task_ids:

                child = self.get_task(child_id)

                if child is not None:
                    cancel_recursive(child)

        cancel_recursive(task)

        return cancelled_ids

    def clear(self) -> None:

        self.tasks.clear()

    def all(self) -> list[Task]:

        return list(self.tasks)


task_engine = TaskEngine()