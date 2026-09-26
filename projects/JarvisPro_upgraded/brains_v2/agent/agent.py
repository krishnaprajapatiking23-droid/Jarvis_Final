"""
Jarvis Agent

==========================================
JARVIS PRO - autonomous agent loop
==========================================

Roadmap section 18 (autonomous agent) tied together with planning (1),
execution (10), verification (19), self-correction (20), policy (11),
background execution (17) and observability (39).

Loop:

    goal -> plan -> policy check -> execute step -> verify
         -> on failure: retry / fix / re-plan / ask / abort
         -> report

Backward compatible: ``agent.run(goal)`` still returns a list of step
results. ``agent.run_goal(goal)`` returns the full structured report, and
``agent.run_background(goal)`` queues the same work without blocking.
"""

from __future__ import annotations

import threading
import time
from typing import Any, Callable

from .executor import executor
from .planner import planner


class Agent:

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._history: list[dict[str, Any]] = []

    # ---------------------------------------------------- main loop

    def run_goal(
        self,
        goal: str,
        cancel: threading.Event | None = None,
        on_progress: Callable[[str], None] | None = None,
        allow_replan: bool = True,
        confirmed: bool = False,
    ) -> dict[str, Any]:
        """Run a goal end to end and return a structured report."""

        from brains_v2.agent.error_handler import ASK, REPLAN, SKIP, ABORT
        from core.observability import observability

        started = time.time()
        goal = str(goal or "").strip()

        observability.new_trace(f"agent: {goal[:60]}")

        if not goal:
            return {
                "ok": False,
                "goal": goal,
                "message": "Tell me what you want me to do.",
                "steps": [],
            }

        def progress(message: str) -> None:
            if on_progress is not None:
                try:
                    on_progress(message)

                except Exception:
                    pass

        plan = planner.create_plan(goal)

        progress(plan.visualise())

        if plan.needs_confirmation and not confirmed:
            return {
                "ok": False,
                "goal": goal,
                "needs_confirmation": True,
                "plan": plan.report(),
                "message": (
                    "This plan includes a risky step. "
                    "Confirm it and I will continue."
                ),
                "steps": [],
            }

        results: list[dict[str, Any]] = []
        completed: list[str] = []
        replans = 0
        index = 0
        steps = list(plan.steps)

        while index < len(steps):
            if cancel is not None and cancel.is_set():
                return self._finish(
                    goal, plan, results, started, False, "Task cancelled."
                )

            step = steps[index]

            progress(f"Step {index + 1}/{len(steps)}: {step.action}")

            outcome = executor.run_step(step, cancel=cancel)
            outcome["index"] = index + 1
            results.append(outcome)

            if outcome["ok"]:
                completed.append(step.action)
                index += 1
                continue

            if outcome.get("cancelled"):
                return self._finish(
                    goal, plan, results, started, False, "Task cancelled."
                )

            if outcome.get("needs_confirmation"):
                return self._finish(
                    goal,
                    plan,
                    results,
                    started,
                    False,
                    f"I need your permission: {outcome['error']}",
                    needs_confirmation=True,
                )

            decision = str(outcome.get("decision", {}).get("decision", SKIP))

            if decision == ABORT:
                return self._finish(
                    goal,
                    plan,
                    results,
                    started,
                    False,
                    f"I stopped: {outcome['error']}",
                )

            if decision == ASK:
                return self._finish(
                    goal,
                    plan,
                    results,
                    started,
                    False,
                    outcome.get("decision", {}).get("reason", outcome["error"]),
                    needs_user=True,
                )

            if decision == REPLAN and allow_replan and replans < 2:
                replans += 1

                progress("That did not work - building a new plan.")

                plan = planner.replan(
                    goal,
                    completed=completed,
                    failed_step=step.action,
                    error=outcome["error"],
                )
                steps = list(plan.steps)
                index = 0
                continue

            # SKIP / exhausted retries
            index += 1

        succeeded = [item for item in results if item["ok"]]

        return self._finish(
            goal,
            plan,
            results,
            started,
            bool(succeeded) and len(succeeded) == len(results),
            self._summarise(results),
            replans=replans,
        )

    def _summarise(self, results: list[dict[str, Any]]) -> str:
        done = [item for item in results if item["ok"]]
        failed = [item for item in results if not item["ok"]]

        if not results:
            return "There was nothing to do."

        if not failed:
            last = str(done[-1].get("output") or "").strip()

            return last or f"Done - {len(done)} step(s) completed."

        return (
            f"{len(done)} of {len(results)} steps completed. "
            f"Problem: {failed[-1]['error']}"
        )

    def _finish(
        self,
        goal: str,
        plan: Any,
        results: list[dict[str, Any]],
        started: float,
        ok: bool,
        message: str,
        **extra: Any,
    ) -> dict[str, Any]:
        from core.observability import observability

        report = {
            "ok": ok,
            "goal": goal,
            "message": message,
            "plan": plan.report() if hasattr(plan, "report") else {},
            "steps": results,
            "duration": round(time.time() - started, 2),
            **extra,
        }

        with self._lock:
            self._history.append(
                {
                    "at": time.time(),
                    "goal": goal,
                    "ok": ok,
                    "steps": len(results),
                    "duration": report["duration"],
                    "message": message[:300],
                }
            )

            del self._history[:-100]

        observability.record(
            "agent.goal",
            report["duration"],
            ok=ok,
            error="" if ok else message[:200],
            steps=len(results),
        )

        return report

    # ---------------------------------------------------- background

    def run_background(self, goal: str, priority: int | None = None) -> str:
        """Queue a goal and return the task id immediately."""

        from brains_v2.agent.task_queue import NORMAL, queue

        def handler(task: Any = None) -> Any:
            cancel = getattr(task, "cancel_flag", None)

            def progress(message: str) -> None:
                if task is not None:
                    task.progress = message

            return self.run_goal(goal, cancel=cancel, on_progress=progress)

        return queue.submit(
            goal,
            handler,
            priority=priority if priority is not None else NORMAL,
        )

    def status(self, task_id: str) -> dict[str, Any]:
        from brains_v2.agent.task_queue import queue

        return queue.status(task_id)

    def cancel(self, task_id: str) -> bool:
        from brains_v2.agent.task_queue import queue

        return queue.cancel(task_id)

    def history(self, limit: int = 10) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._history[-limit:])

    # ---------------------------------------------------- legacy api

    def run(self, goal: str) -> list[Any]:
        """Original API - a list of per-step outputs."""

        report = self.run_goal(goal, confirmed=True)

        if not report["steps"]:
            return [report["message"]]

        return [
            item["output"] if item["ok"] else f"Failed: {item['error']}"
            for item in report["steps"]
        ]


agent = Agent()
