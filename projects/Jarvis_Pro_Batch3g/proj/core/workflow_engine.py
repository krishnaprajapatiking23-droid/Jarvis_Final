"""
==========================================
JARVIS PRO
Workflow automation
==========================================

Roadmap section 38 (workflow automation): save a sequence of steps once, then
run it by name, on demand or in the background.

Workflows are plain JSON, so you can edit them by hand, and each step is
either a registered tool or a plain instruction handled by the agent.

    from core.workflow_engine import workflows

    workflows.create("morning", [
        {"tool": "system_status"},
        {"action": "summarise my reminders for today"},
    ], description="Morning routine")

    workflows.run("morning")
    workflows.run_background("morning")

Every run is policy-checked through the tool registry, recorded as an
experience, and reports per-step results.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any


MAX_STEPS = 25


class WorkflowEngine:
    """Named, reusable multi-step routines."""

    def __init__(self) -> None:
        self._lock = threading.RLock()

    # ---------------------------------------------------- storage

    def _path(self) -> Path:
        try:
            from config import config

            return config.data_path() / "workflows.json"

        except Exception:
            return Path("data/workflows.json")

    def _load(self) -> dict[str, Any]:
        path = self._path()

        if not path.exists():
            return {}

        try:
            data = json.loads(path.read_text(encoding="utf-8"))

            return data if isinstance(data, dict) else {}

        except Exception:
            return {}

    def _save(self, data: dict[str, Any]) -> bool:
        path = self._path()

        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
            )

            return True

        except Exception:
            return False

    def _clean_name(self, name: str) -> str:
        return " ".join(str(name or "").strip().lower().split())

    # ---------------------------------------------------- editing

    def create(
        self,
        name: str,
        steps: list[dict[str, Any]],
        description: str = "",
        overwrite: bool = True,
    ) -> dict[str, Any]:
        """Save a workflow. Steps use 'tool' + 'arguments', or 'action'."""

        key = self._clean_name(name)

        if not key:
            return {"ok": False, "error": "a workflow needs a name"}

        cleaned: list[dict[str, Any]] = []

        for step in list(steps or [])[:MAX_STEPS]:
            if isinstance(step, str):
                cleaned.append({"action": step, "tool": "", "arguments": {}})
                continue

            if not isinstance(step, dict):
                continue

            tool = str(step.get("tool") or "").strip()
            action = str(step.get("action") or "").strip()
            arguments = step.get("arguments")

            if not tool and not action:
                continue

            cleaned.append(
                {
                    "action": action or f"run {tool}",
                    "tool": tool,
                    "arguments": dict(arguments)
                    if isinstance(arguments, dict)
                    else {},
                }
            )

        if not cleaned:
            return {"ok": False, "error": "that workflow has no usable steps"}

        with self._lock:
            data = self._load()

            if key in data and not overwrite:
                return {
                    "ok": False,
                    "error": f"a workflow called '{key}' already exists",
                }

            data[key] = {
                "name": key,
                "description": str(description or "")[:300],
                "steps": cleaned,
                "created": data.get(key, {}).get("created", time.time()),
                "updated": time.time(),
                "runs": int(data.get(key, {}).get("runs", 0)),
                "last_run": data.get(key, {}).get("last_run", 0),
            }

            if not self._save(data):
                return {"ok": False, "error": "could not save the workflow file"}

        return {"ok": True, "name": key, "steps": len(cleaned)}

    def delete(self, name: str) -> bool:
        key = self._clean_name(name)

        with self._lock:
            data = self._load()

            if key not in data:
                return False

            data.pop(key, None)

            return self._save(data)

    def rename(self, old: str, new: str) -> bool:
        source = self._clean_name(old)
        target = self._clean_name(new)

        if not source or not target:
            return False

        with self._lock:
            data = self._load()

            if source not in data or target in data:
                return False

            data[target] = {**data.pop(source), "name": target}

            return self._save(data)

    # ---------------------------------------------------- reading

    def names(self) -> list[str]:
        return sorted(self._load())

    def get(self, name: str) -> dict[str, Any] | None:
        return self._load().get(self._clean_name(name))

    def has(self, name: str) -> bool:
        return self._clean_name(name) in self._load()

    def describe(self, name: str) -> str:
        workflow = self.get(name)

        if workflow is None:
            return f"I have no workflow called '{name}'."

        lines = [f"Workflow '{workflow['name']}' ({len(workflow['steps'])} steps)"]

        if workflow.get("description"):
            lines.append(workflow["description"])

        for index, step in enumerate(workflow["steps"], start=1):
            tool = f" [{step['tool']}]" if step.get("tool") else ""
            lines.append(f"  {index}. {step['action']}{tool}")

        return "\n".join(lines)

    # ---------------------------------------------------- running

    def run(
        self,
        name: str,
        cancel: threading.Event | None = None,
        stop_on_failure: bool = True,
    ) -> dict[str, Any]:
        """Run every step in order and report what happened."""

        workflow = self.get(name)

        if workflow is None:
            return {
                "ok": False,
                "error": f"I have no workflow called '{name}'",
                "steps": [],
            }

        started = time.time()
        results: list[dict[str, Any]] = []

        from brains_v2.agent.executor import executor
        from brains_v2.agent.planner import Step

        for index, raw in enumerate(workflow["steps"], start=1):
            if cancel is not None and cancel.is_set():
                results.append(
                    {"index": index, "ok": False, "error": "cancelled"}
                )
                break

            step = Step(
                action=str(raw.get("action") or ""),
                tool=str(raw.get("tool") or ""),
                arguments=dict(raw.get("arguments") or {}),
            )
            outcome = executor.run_step(step, cancel=cancel)
            results.append({"index": index, **outcome})

            if not outcome["ok"] and stop_on_failure:
                break

        succeeded = sum(1 for item in results if item.get("ok"))
        ok = bool(results) and succeeded == len(workflow["steps"])
        duration = round(time.time() - started, 2)

        with self._lock:
            data = self._load()

            if workflow["name"] in data:
                data[workflow["name"]]["runs"] = int(
                    data[workflow["name"]].get("runs", 0)
                ) + 1
                data[workflow["name"]]["last_run"] = time.time()
                self._save(data)

        try:
            from memory.experience import experience

            experience.record(
                f"workflow {workflow['name']}",
                success=ok,
                steps=len(results),
                duration=duration,
                strategy="workflow",
                error="" if ok else str(results[-1].get("error", "")) if results else "",
            )

        except Exception:
            pass

        try:
            from core.event_bus import event_bus

            event_bus.publish(
                "workflow.finished",
                {"name": workflow["name"], "ok": ok, "steps": len(results)},
            )

        except Exception:
            pass

        return {
            "ok": ok,
            "name": workflow["name"],
            "steps": results,
            "completed": succeeded,
            "total": len(workflow["steps"]),
            "duration": duration,
            "message": (
                f"Workflow '{workflow['name']}' finished all "
                f"{len(workflow['steps'])} steps."
                if ok
                else f"Workflow '{workflow['name']}' completed "
                f"{succeeded} of {len(workflow['steps'])} steps."
            ),
        }

    def run_background(self, name: str) -> str:
        """Queue a workflow and return the task id."""

        from brains_v2.agent.task_queue import queue

        def handler(task: Any = None) -> Any:
            return self.run(name, cancel=getattr(task, "cancel_flag", None))

        return queue.submit(f"workflow {self._clean_name(name)}", handler)

    def status(self) -> dict[str, Any]:
        data = self._load()

        return {
            "count": len(data),
            "names": sorted(data),
            "total_runs": sum(int(item.get("runs", 0)) for item in data.values()),
            "file": str(self._path()),
        }


workflows = WorkflowEngine()
