"""
Task Engine with Failure Recovery, Re-Planning, and Situation Awareness
"""

from __future__ import annotations

from typing import Any


class TaskEngine:

    def __init__(self):

        self.tasks = []
        self.current_index = None
        self.last_result = None

    def add(self, task):

        self.tasks.append({
            "task": task,
            "done": False,
            "failed": False,
            "running": False,
            "error": None
        })

    def start(self, index):

        if 0 <= index < len(self.tasks):

            self.current_index = index
            self.tasks[index]["running"] = True
            self.tasks[index]["done"] = False
            self.tasks[index]["failed"] = False

    def complete(self, index, result=None):

        if 0 <= index < len(self.tasks):

            self.tasks[index]["done"] = True
            self.tasks[index]["failed"] = False
            self.tasks[index]["running"] = False
            self.tasks[index]["error"] = None

            self.current_index = index
            self.last_result = result

    def fail(self, index, error=None):

        if 0 <= index < len(self.tasks):

            self.tasks[index]["done"] = False
            self.tasks[index]["failed"] = True
            self.tasks[index]["running"] = False
            self.tasks[index]["error"] = error

            self.current_index = index
            self.last_result = None

    def replan(self, index):

        if not (0 <= index < len(self.tasks)):
            return None

        task = self.tasks[index]

        if not task["failed"]:
            return None

        alternative = {
            "original_task": task["task"],
            "reason": task["error"],
            "alternative_task": (
                f"Retry {task['task']} using an alternative approach"
            ),
            "status": "pending"
        }

        return alternative

    def situation(self) -> dict[str, Any]:

        current_task = None

        if (
            self.current_index is not None
            and 0 <= self.current_index < len(self.tasks)
        ):
            current_task = self.tasks[self.current_index]

        if current_task is None:
            state = "idle"
        elif current_task["failed"]:
            state = "failed"
        elif current_task["running"]:
            state = "running"
        elif current_task["done"]:
            state = "completed"
        else:
            state = "pending"

        return {
            "state": state,
            "current_task": current_task,
            "task_count": len(self.tasks),
            "pending_count": len(self.pending()),
            "failed_count": len(self.failed()),
            "completed_count": len(self.completed()),
            "last_result": self.last_result
        }

    def pending(self):

        return [
            task for task in self.tasks
            if not task["done"] and not task["failed"]
        ]

    def failed(self):

        return [
            task for task in self.tasks
            if task["failed"]
        ]

    def completed(self):

        return [
            task for task in self.tasks
            if task["done"]
        ]


task_engine = TaskEngine()