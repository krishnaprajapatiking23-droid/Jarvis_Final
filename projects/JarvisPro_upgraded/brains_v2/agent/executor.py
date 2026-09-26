"""
Task Executor

==========================================
JARVIS PRO - execution engine
==========================================

Roadmap sections 10 (execution engine) and 19 (verification engine).

Backward compatible: ``executor.execute(task)`` still accepts a plain string
and still returns the assistant's answer text, so existing callers such as
``brains_v2.agent.agent`` are unaffected.

What was added:
  * tool steps are routed through ``core.tool_schema`` (policy checked);
  * reasoning steps go through ``core.model_router`` with the existing LLM
    assistant kept as the fallback;
  * every step is verified, timed and retried according to
    ``brains_v2.agent.error_handler``;
  * co-operative cancellation through a cancel event.
"""

from __future__ import annotations

import threading
import time
from typing import Any


class Executor:

    # ---------------------------------------------------- helpers

    def _max_retries(self) -> int:
        try:
            from config import config

            return max(int(config.get("agent.max_retries", 2)), 1)

        except Exception:
            return 2

    def _ask_model(self, prompt: str) -> str:
        """Model answer with the project's own assistant as fallback."""

        try:
            from core.model_router import router

            text = router.text(prompt, capability="chat")

            if text:
                return text

        except Exception:
            pass

        from brains_v2.llm.assistant import assistant

        return assistant.ask(prompt)

    def _run_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        from core.tool_schema import tool_registry

        return tool_registry.run(name, **(arguments or {}))

    # ---------------------------------------------------- verification

    def verify(self, step: Any, output: Any) -> dict[str, Any]:
        """Cheap, offline verification of a step result."""

        criterion = str(getattr(step, "success", "") or "").strip()

        if isinstance(output, dict):
            if output.get("ok") is False:
                return {
                    "ok": False,
                    "reason": str(output.get("error") or "the step reported failure"),
                }

            payload = output.get("result", output)

        else:
            payload = output

        text = str(payload or "").strip()

        if not text:
            return {"ok": False, "reason": "the step produced no output"}

        lowered = text.lower()

        # Only unmistakable failure signatures count. A tool that politely
        # reports a missing optional package still ran successfully.
        for marker in (
            "traceback (most recent call last)",
            "unhandled exception",
        ):
            if marker in lowered:
                return {"ok": False, "reason": "the output contains a crash"}

        return {"ok": True, "reason": criterion or "output produced"}

    # ---------------------------------------------------- running

    def run_step(
        self,
        step: Any,
        cancel: threading.Event | None = None,
    ) -> dict[str, Any]:
        """Execute one step with retries, verification and telemetry.

        Returns ``{"ok", "output", "attempts", "error", "decision", "step"}``.
        """

        from brains_v2.agent.error_handler import error_handler
        from core.observability import observability

        action = str(getattr(step, "action", step) or "").strip()
        tool = str(getattr(step, "tool", "") or "").strip()
        arguments = dict(getattr(step, "arguments", {}) or {})

        attempts = 0
        last_error = ""
        decision_report: dict[str, Any] = {}
        max_attempts = self._max_retries()

        while attempts < max_attempts:
            if cancel is not None and cancel.is_set():
                return {
                    "ok": False,
                    "output": "",
                    "attempts": attempts,
                    "error": "cancelled",
                    "cancelled": True,
                    "step": action,
                }

            attempts += 1
            started = time.time()

            try:
                if tool:
                    result = self._run_tool(tool, arguments)

                    if not result.get("ok") and result.get("needs_confirmation"):
                        return {
                            "ok": False,
                            "output": "",
                            "attempts": attempts,
                            "error": result.get("error", "confirmation required"),
                            "needs_confirmation": True,
                            "risk": result.get("risk", ""),
                            "action": result.get("action", ""),
                            "step": action,
                        }

                    output: Any = result

                else:
                    output = self._ask_model(action)

                check = self.verify(step, output)

                observability.record(
                    "agent.step",
                    time.time() - started,
                    ok=bool(check["ok"]),
                    error="" if check["ok"] else check["reason"],
                    tool=tool,
                )

                if check["ok"]:
                    return {
                        "ok": True,
                        "output": output.get("result", output)
                        if isinstance(output, dict)
                        else output,
                        "attempts": attempts,
                        "error": "",
                        "verified": check["reason"],
                        "step": action,
                    }

                last_error = check["reason"]

            except Exception as error:
                last_error = f"{type(error).__name__}: {error}"

                observability.record(
                    "agent.step",
                    time.time() - started,
                    ok=False,
                    error=last_error,
                    tool=tool,
                )

            decision = error_handler.analyze(action, last_error, attempts)
            decision_report = decision.report()

            if not decision.should_retry:
                break

            if decision.retry_after:
                waited = 0.0

                while waited < decision.retry_after:
                    if cancel is not None and cancel.is_set():
                        break

                    time.sleep(0.1)
                    waited += 0.1

        return {
            "ok": False,
            "output": "",
            "attempts": attempts,
            "error": last_error or "the step did not succeed",
            "decision": decision_report,
            "step": action,
        }

    # ---------------------------------------------------- legacy api

    def execute(self, task: Any) -> Any:
        """Original API - returns the answer text (or the tool result)."""

        result = self.run_step(task)

        if result["ok"]:
            return result["output"]

        if result.get("needs_confirmation"):
            return f"I need your confirmation first: {result['error']}"

        return f"I could not complete that step: {result['error']}"


executor = Executor()
