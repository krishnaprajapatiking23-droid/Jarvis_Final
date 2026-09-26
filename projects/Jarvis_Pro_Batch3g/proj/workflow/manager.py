"""
Workflow Manager — builds and executes multi-step workflows.

A workflow is a sequence of named steps; each step can succeed, fail,
or branch to a sub-workflow.
"""

import time
from enum import Enum
from threading import Lock
from typing import Any, Callable, Dict, List, Optional


class StepStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"


class WorkflowStep:
    def __init__(self, name: str, action: Callable = None,
                 on_failure: str = None):
        self.name = name
        self.action = action
        self.on_failure = on_failure  # name of step to jump to on failure
        self.status = StepStatus.PENDING
        self.result = None
        self.error: Optional[str] = None
        self.started_at: Optional[float] = None
        self.finished_at: Optional[float] = None

    def run(self) -> "WorkflowStep":
        self.status = StepStatus.RUNNING
        self.started_at = time.time()
        try:
            self.result = self.action() if self.action else None
            self.status = StepStatus.DONE
        except Exception as e:
            self.status = StepStatus.FAILED
            self.error = str(e)
        finally:
            self.finished_at = time.time()
        return self

    def duration_ms(self) -> float:
        if self.started_at and self.finished_at:
            return round((self.finished_at - self.started_at) * 1000, 2)
        return 0.0


class Workflow:
    def __init__(self, name: str):
        self.name = name
        self.steps: List[WorkflowStep] = []
        self._current = -1
        self._status = StepStatus.PENDING

    def add(self, name: str, action: Callable = None,
            on_failure: str = None) -> "Workflow":
        self.steps.append(WorkflowStep(name, action, on_failure))
        return self

    def execute(self) -> Dict[str, Any]:
        self._status = StepStatus.RUNNING
        for i, step in enumerate(self.steps):
            step.run()
            self._current = i
            if step.status == StepStatus.FAILED:
                # Look for failure handler step
                handler = next(
                    (s for s in self.steps if s.name == step.on_failure),
                    None)
                if handler:
                    handler.run()
                self._status = StepStatus.FAILED
                break
        else:
            self._status = StepStatus.DONE
        return self.report()

    def report(self) -> Dict[str, Any]:
        return {
            "workflow": self.name,
            "status": self._status.value,
            "current_step": (
                self.steps[self._current].name
                if 0 <= self._current < len(self.steps) else None
            ),
            "steps": [
                {
                    "name": s.name,
                    "status": s.status.value,
                    "duration_ms": s.duration_ms(),
                    "error": s.error,
                    "result": str(s.result)[:100] if s.result else None,
                }
                for s in self.steps
            ],
        }


class WorkflowManager:
    """Manages named workflows and their executions."""

    def __init__(self):
        self._workflows: Dict[str, Workflow] = {}
        self._history: List[Dict] = []
        self._lock = Lock()

    def define(self, name: str) -> Workflow:
        """Create or replace a workflow by name."""
        wf = Workflow(name)
        self._workflows[name] = wf
        return wf

    def run(self, name: str) -> Dict[str, Any]:
        """Execute a named workflow."""
        wf = self._workflows.get(name)
        if not wf:
            return {"error": f"Workflow '{name}' not found"}
        result = wf.execute()
        with self._lock:
            self._history.append(result)
        return result

    def list_workflows(self) -> List[str]:
        return list(self._workflows.keys())

    def history(self, limit: int = 20) -> List[Dict]:
        return self._history[-limit:]


_manager = WorkflowManager()

define = _manager.define
run = _manager.run
list_workflows = _manager.list_workflows
history = _manager.history
