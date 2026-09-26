"""
==========================================
JARVIS PRO
Intelligence loop
==========================================

Roadmap sections 41 and 42: the single loop that ties every subsystem
together.

    YOU -> INPUT -> UNDERSTAND -> CONTEXT -> MEMORY -> PROFILE -> PRIORITY
    -> POLICY -> DECISION -> PLAN -> EXECUTION -> OBSERVE -> VERIFY
    -> LEARN + CORRECT -> EXPERIENCE -> REPORT

This module owns no intelligence of its own. It is the conductor: it calls the
existing engines in the right order, passes what each one learned to the next,
and records the whole journey so it can be explained afterwards.

    from core.intelligence_loop import loop

    result = loop.handle("check my system health and tell me if anything is wrong")
    print(result["reply"])
    print(loop.explain())     # every stage, in order, with what it decided

Every stage is wrapped so a missing subsystem degrades the loop instead of
breaking it.
"""

from __future__ import annotations

import threading
import time
from typing import Any


STAGES = (
    "input",
    "understand",
    "context",
    "memory",
    "profile",
    "priority",
    "policy",
    "decision",
    "plan",
    "execution",
    "observe",
    "verify",
    "learn",
    "experience",
    "report",
)

HISTORY_LIMIT = 20


class IntelligenceLoop:
    """Runs one request through every stage of the JARVIS pipeline."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._history: list[dict[str, Any]] = []
        self._last: dict[str, Any] = {}

    # ---------------------------------------------------- helpers

    def _stage(
        self, trace: list[dict[str, Any]], name: str, detail: Any
    ) -> None:
        trace.append(
            {
                "stage": name,
                "detail": detail,
                "at": round(time.time(), 3),
            }
        )

    # ---------------------------------------------------- stages

    def _understand(self, text: str) -> dict[str, Any]:
        """What kind of request is this, and does it change how I speak?"""

        lowered = text.lower()
        kind = "question"

        if any(
            word in lowered
            for word in ("open", "run", "create", "delete", "send", "install", "close")
        ):
            kind = "action"

        elif any(word in lowered for word in ("remind", "schedule", "tomorrow")):
            kind = "scheduling"

        elif any(word in lowered for word in ("remember", "note", "save")):
            kind = "memory"

        style: dict[str, Any] = {}

        try:
            from personality.modes import personality

            style = personality.apply_request(text)

        except Exception:
            style = {}

        return {"kind": kind, "words": len(text.split()), "style_change": style}

    def _context(self, text: str) -> str:
        try:
            from core.context_engine import context_engine

            return context_engine.assemble(text)

        except Exception:
            return ""

    def _memory(self, text: str) -> dict[str, Any]:
        found: dict[str, Any] = {"facts": [], "advice": ""}

        try:
            from memory.knowledge_base import knowledge

            found["facts"] = [
                item.get("fact", "") for item in knowledge.search(text, limit=3)
            ]

        except Exception:
            pass

        try:
            from memory.experience import experience

            found["advice"] = experience.advice(text)

        except Exception:
            pass

        return found

    def _profile(self) -> dict[str, Any]:
        try:
            from config import config

            return {
                "owner": config.get("assistant.owner", ""),
                "language": config.get("assistant.language", "en"),
            }

        except Exception:
            return {}

    def _priority(self, text: str, kind: str) -> dict[str, Any]:
        lowered = text.lower()
        score = 5

        if any(word in lowered for word in ("urgent", "now", "immediately", "asap")):
            score += 3

        if kind == "action":
            score += 1

        if any(word in lowered for word in ("later", "sometime", "whenever")):
            score -= 2

        score = max(1, min(score, 10))

        return {
            "score": score,
            "foreground": score >= 4,
        }

    def _policy(self, text: str) -> dict[str, Any]:
        try:
            from security.policy_engine import policy

            verdict = policy.check("agent_request", {"request": text}).report()

            return {
                "allowed": bool(verdict.get("allowed", True)),
                "risk": verdict.get("risk", "low"),
                "reason": verdict.get("reason", ""),
                "needs_confirmation": bool(verdict.get("needs_confirmation", False)),
            }

        except Exception:
            return {"allowed": True, "risk": "unknown", "reason": ""}

    def _decide(
        self, kind: str, priority: dict[str, Any], policy: dict[str, Any]
    ) -> dict[str, Any]:
        if not policy.get("allowed", True):
            return {"route": "refuse", "why": policy.get("reason", "blocked by policy")}

        if policy.get("needs_confirmation"):
            return {"route": "confirm", "why": "this needs your confirmation first"}

        if kind == "action" or priority["score"] >= 7:
            return {"route": "agent", "why": "the request needs real steps taken"}

        return {"route": "agent", "why": "handled through the planning agent"}

    # ---------------------------------------------------- main loop

    def handle(self, text: str, background: bool = False) -> dict[str, Any]:
        """Run one request through the whole loop."""

        started = time.time()
        request = str(text or "").strip()
        trace: list[dict[str, Any]] = []

        if not request:
            return {
                "ok": False,
                "reply": "I did not catch a request there.",
                "trace": trace,
            }

        self._stage(trace, "input", {"request": request})

        understanding = self._understand(request)
        self._stage(trace, "understand", understanding)

        context = self._context(request)
        self._stage(trace, "context", {"characters": len(context)})

        memory = self._memory(request)
        self._stage(trace, "memory", memory)

        profile = self._profile()
        self._stage(trace, "profile", profile)

        priority = self._priority(request, understanding["kind"])
        self._stage(trace, "priority", priority)

        permission = self._policy(request)
        self._stage(trace, "policy", permission)

        decision = self._decide(understanding["kind"], priority, permission)
        self._stage(trace, "decision", decision)

        if decision["route"] in {"refuse", "confirm"}:
            reply = (
                f"I am not going to do that: {decision['why']}."
                if decision["route"] == "refuse"
                else f"Before I continue - {decision['why']}."
            )
            outcome = {
                "ok": False,
                "reply": reply,
                "route": decision["route"],
                "trace": trace,
                "duration": round(time.time() - started, 2),
            }
            self._remember(outcome, request)

            return outcome

        # ------------------------------------------------ background
        if background or not priority["foreground"]:
            try:
                from brains_v2.agent.task_queue import queue

                task_id = queue.submit(
                    request,
                    lambda task=None: self._run_agent(request, context, memory),
                )
                self._stage(trace, "execution", {"background_task": task_id})

                outcome = {
                    "ok": True,
                    "reply": "I will handle that in the background and report back.",
                    "route": "background",
                    "task_id": task_id,
                    "trace": trace,
                    "duration": round(time.time() - started, 2),
                }
                self._remember(outcome, request)

                return outcome

            except Exception as problem:
                self._stage(trace, "execution", {"background_failed": str(problem)})

        # ------------------------------------------------ foreground
        execution = self._run_agent(request, context, memory)
        self._stage(
            trace,
            "execution",
            {"steps": execution.get("steps", 0), "ok": execution.get("ok")},
        )

        self._stage(trace, "observe", self._observe())

        verified = bool(execution.get("ok"))
        self._stage(
            trace,
            "verify",
            {
                "verified": verified,
                "error": str(execution.get("error", ""))[:200],
            },
        )

        learned = self._learn(request, execution)
        self._stage(trace, "learn", learned)

        recorded = self._record(request, execution, time.time() - started)
        self._stage(trace, "experience", recorded)

        outcome = {
            "ok": verified,
            "reply": str(execution.get("reply") or ""),
            "route": "agent",
            "steps": execution.get("steps", 0),
            "priority": priority["score"],
            "risk": permission.get("risk", "low"),
            "trace": trace,
            "duration": round(time.time() - started, 2),
        }

        self._stage(
            trace,
            "report",
            {"ok": outcome["ok"], "duration": outcome["duration"]},
        )
        self._remember(outcome, request)

        return outcome

    # ---------------------------------------------------- sub-steps

    def _run_agent(
        self, request: str, context: str, memory: dict[str, Any]
    ) -> dict[str, Any]:
        """Hand the request to the planning agent with everything gathered."""

        hints: list[str] = []

        if context:
            hints.append(context)

        if memory.get("facts"):
            hints.append("Known facts: " + "; ".join(memory["facts"]))

        if memory.get("advice"):
            hints.append(str(memory["advice"]))

        try:
            from brains_v2.agent.agent import agent

            goal = request

            if hints:
                goal = request + "\n\nUseful context:\n" + "\n".join(hints)

            result = agent.run_goal(goal)

            if isinstance(result, dict):
                steps = result.get("steps")
                failed = [
                    str(item.get("error", ""))
                    for item in (steps if isinstance(steps, list) else [])
                    if isinstance(item, dict) and not item.get("ok", True)
                ]

                return {
                    "ok": bool(result.get("ok", True)),
                    "reply": str(result.get("message") or ""),
                    "steps": len(steps) if isinstance(steps, list) else 0,
                    "error": failed[0] if failed else "",
                }

            return {"ok": True, "reply": str(result), "steps": 0, "error": ""}

        except Exception as problem:
            return {
                "ok": False,
                "reply": "I could not complete that request.",
                "steps": 0,
                "error": str(problem),
            }

    def _observe(self) -> dict[str, Any]:
        try:
            from core.observability import observability

            return observability.health()

        except Exception:
            return {}

    def _learn(self, request: str, execution: dict[str, Any]) -> dict[str, Any]:
        learned: dict[str, Any] = {"mistake_logged": False, "fact_learned": False}

        if not execution.get("ok") and execution.get("error"):
            try:
                from learning.mistakes import mistakes

                mistakes.record(request, str(execution["error"]))
                learned["mistake_logged"] = True

            except Exception:
                pass

        elif execution.get("reply"):
            try:
                from memory.knowledge_base import knowledge

                reply = str(execution["reply"]).strip()

                if 20 < len(reply) < 400:
                    knowledge.learn(reply, source="experience", topic="results")
                    learned["fact_learned"] = True

            except Exception:
                pass

        return learned

    def _record(
        self, request: str, execution: dict[str, Any], duration: float
    ) -> dict[str, Any]:
        try:
            from memory.experience import experience

            experience.record(
                request,
                success=bool(execution.get("ok")),
                steps=int(execution.get("steps") or 0),
                duration=round(duration, 2),
                strategy="intelligence_loop",
                error=str(execution.get("error", "")),
            )

            return {"recorded": True}

        except Exception as problem:
            return {"recorded": False, "reason": str(problem)}

    def _remember(self, outcome: dict[str, Any], request: str) -> None:
        with self._lock:
            self._last = {**outcome, "request": request}
            self._history.append(
                {
                    "request": request,
                    "ok": outcome.get("ok"),
                    "route": outcome.get("route"),
                    "duration": outcome.get("duration"),
                    "at": time.time(),
                }
            )

            if len(self._history) > HISTORY_LIMIT:
                del self._history[:-HISTORY_LIMIT]

    # ---------------------------------------------------- explaining

    def explain(self) -> str:
        """Plain-language walkthrough of the last request."""

        with self._lock:
            last = dict(self._last)

        if not last:
            return "I have not handled a request through the loop yet."

        lines = [f"Request: {last.get('request', '')}", ""]

        for entry in last.get("trace", []):
            lines.append(f"{entry['stage'].upper()}: {entry['detail']}")

        lines.append("")
        lines.append(
            f"Outcome: {'success' if last.get('ok') else 'not completed'} "
            f"in {last.get('duration', 0)}s via {last.get('route', 'unknown')}."
        )

        return "\n".join(lines)

    def history(self, limit: int = 10) -> list[dict[str, Any]]:
        with self._lock:
            return self._history[-limit:]

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "stages": list(STAGES),
                "handled": len(self._history),
                "last_ok": self._last.get("ok") if self._last else None,
            }


loop = IntelligenceLoop()
intelligence_loop = loop
