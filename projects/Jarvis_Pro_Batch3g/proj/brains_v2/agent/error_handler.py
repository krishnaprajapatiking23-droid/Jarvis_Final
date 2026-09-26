"""
==========================================
JARVIS PRO
Agent error handler / self-correction
==========================================

Roadmap sections 19-20 (verification, self-correction, retry, re-planning).

Adapted from Mark-XXXIX-OR ``agent/error_handler.py``: classify a failure
and decide what the agent should do next. The heuristic classifier works
with no model at all; when a model is reachable it is asked for a second
opinion on unclear errors.

Decisions:

    RETRY    transient - try the same step again
    FIX      the step needs different arguments (suggestion provided)
    REPLAN   the plan itself was wrong - ask the planner again
    SKIP     non-essential step, continue the plan
    ASK      needs the user (permission, credential, missing information)
    ABORT    cannot continue safely
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from core.observability import observability


RETRY = "RETRY"
FIX = "FIX"
REPLAN = "REPLAN"
SKIP = "SKIP"
ASK = "ASK"
ABORT = "ABORT"


@dataclass
class ErrorDecision:
    decision: str
    reason: str
    category: str
    retry_after: float = 0.0
    suggestion: str = ""

    @property
    def should_retry(self) -> bool:
        return self.decision in (RETRY, FIX)

    def report(self) -> dict[str, Any]:
        return {
            "decision": self.decision,
            "reason": self.reason,
            "category": self.category,
            "retry_after": self.retry_after,
            "suggestion": self.suggestion,
        }


# category -> (patterns, decision, reason, retry delay)
RULES: list[tuple[str, tuple[str, ...], str, str, float]] = [
    (
        "network",
        ("timeout", "timed out", "connection", "unreachable", "dns", "socket",
         "temporarily unavailable", "502", "503", "504"),
        RETRY,
        "This looks like a temporary network problem.",
        3.0,
    ),
    (
        "rate_limit",
        ("rate limit", "rate_limited", "too many requests", "429", "quota"),
        RETRY,
        "The service is rate limiting us - waiting before the retry.",
        30.0,
    ),
    (
        "auth",
        ("unauthorized", "401", "403", "invalid api key", "api key", "forbidden",
         "authentication"),
        ASK,
        "A credential is missing or invalid - add it in config/api_keys.json.",
        0.0,
    ),
    (
        "permission",
        ("permission denied", "access is denied", "not permitted",
         "confirmation required", "protected system path"),
        ASK,
        "This action needs your permission.",
        0.0,
    ),
    (
        "missing_target",
        ("no such file", "filenotfound", "not found", "does not exist",
         "cannot find"),
        FIX,
        "The target does not exist - the step needs a different path or name.",
        0.0,
    ),
    (
        "bad_arguments",
        ("unexpected keyword", "missing 1 required", "typeerror", "invalid argument",
         "valueerror", "keyerror", "validation"),
        FIX,
        "The step was called with the wrong arguments.",
        0.0,
    ),
    (
        "unknown_tool",
        ("there is no tool", "unknown tool", "no plugin called", "not registered"),
        REPLAN,
        "The plan referenced a capability that does not exist.",
        0.0,
    ),
    (
        "dependency",
        ("modulenotfounderror", "no module named", "importerror", "dll load failed"),
        SKIP,
        "An optional dependency is missing, so this step cannot run here.",
        0.0,
    ),
    (
        "model",
        ("no model could answer", "empty response", "model not found",
         "ollama", "server not listening"),
        RETRY,
        "The model was not reachable - retrying once.",
        2.0,
    ),
    (
        "fatal",
        ("memoryerror", "disk full", "no space left", "keyboardinterrupt",
         "systemexit"),
        ABORT,
        "This is not recoverable - stopping the task.",
        0.0,
    ),
]


ANALYST_PROMPT = """You are the error analyst of an autonomous assistant.

STEP: {step}
ERROR: {error}
ATTEMPT: {attempt} of {max_attempts}

Decide what the agent should do. Reply with JSON only:
{{"decision": "RETRY|FIX|REPLAN|SKIP|ASK|ABORT",
  "category": "short label",
  "reason": "one sentence",
  "suggestion": "how to change the step, or empty"}}

Rules:
- RETRY only for transient failures.
- FIX when the same step could work with different arguments.
- REPLAN when the plan itself is wrong.
- ASK when a human, a permission or a credential is required.
- ABORT only when continuing is unsafe or pointless."""


class ErrorHandler:

    def __init__(self, max_attempts: int = 2) -> None:
        self.max_attempts = max(int(max_attempts), 1)

    # ---------------------------------------------------- classification

    def classify(self, error: str) -> tuple[str, str, str, float]:
        """Heuristic classification - fast, offline, deterministic."""

        text = str(error or "").lower()

        for category, patterns, decision, reason, delay in RULES:
            if any(pattern in text for pattern in patterns):
                return category, decision, reason, delay

        return "unknown", RETRY, "Unclear failure - one retry is worth trying.", 1.0

    # ---------------------------------------------------- decision

    def analyze(
        self,
        step: Any,
        error: str,
        attempt: int = 1,
        use_model: bool = True,
    ) -> ErrorDecision:
        """Decide what to do about a failed step."""

        category, decision, reason, delay = self.classify(error)

        if attempt >= self.max_attempts and decision in (RETRY, FIX):
            decision = REPLAN if category in ("missing_target", "bad_arguments") else SKIP
            reason = (
                f"Already tried {attempt} times - "
                + ("re-planning instead." if decision == REPLAN else "moving on.")
            )
            delay = 0.0

        result = ErrorDecision(decision, reason, category, delay)

        if category == "unknown" and use_model:
            refined = self._ask_model(step, error, attempt)

            if refined is not None:
                result = refined

        observability.info(
            "error_handler",
            f"{result.category} -> {result.decision}",
            attempt=attempt,
            error=str(error)[:200],
        )

        return result

    def _ask_model(self, step: Any, error: str, attempt: int) -> ErrorDecision | None:
        try:
            from core.model_router import router

            data = router.json(
                ANALYST_PROMPT.format(
                    step=str(step)[:400],
                    error=str(error)[:600],
                    attempt=attempt,
                    max_attempts=self.max_attempts,
                ),
                capability="chat",
                options={"temperature": 0.1, "num_predict": 300},
            )

        except Exception:
            return None

        if not isinstance(data, dict):
            return None

        decision = str(data.get("decision", "")).strip().upper()

        if decision not in (RETRY, FIX, REPLAN, SKIP, ASK, ABORT):
            return None

        return ErrorDecision(
            decision,
            str(data.get("reason", "")).strip() or "Decided by the error analyst.",
            str(data.get("category", "analysed")).strip() or "analysed",
            2.0 if decision == RETRY else 0.0,
            str(data.get("suggestion", "")).strip(),
        )

    # ---------------------------------------------------- messaging

    def explain(self, decision: ErrorDecision, step: Any = "") -> str:
        """Plain-language explanation for the user."""

        prefix = f"Step '{step}' failed. " if step else ""

        follow_up = {
            RETRY: "I will try again.",
            FIX: "I will adjust the step and retry.",
            REPLAN: "I will build a new plan.",
            SKIP: "I will skip it and continue.",
            ASK: "I need you to decide how to continue.",
            ABORT: "I have stopped this task.",
        }.get(decision.decision, "")

        return f"{prefix}{decision.reason} {follow_up}".strip()


error_handler = ErrorHandler()


def analyze_error(step: Any, error: str, attempt: int = 1) -> ErrorDecision:
    """Module-level helper matching the reference project's API."""

    return error_handler.analyze(step, error, attempt)
