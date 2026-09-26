"""
==========================================
JARVIS PRO
Human-Like Response Controller  (variation features 1, 14, 16, 17, 19, 21, 26, 27, 30)
==========================================

The layer that sits between the AI Brain and JARVIS's final output:

    user input -> understanding -> AI Brain (Ollama)
                                     |
                            response planner  (what shape?)
                                     |
                            style controller  (how to say it / sampling)
                                     |
                              model generation
                                     |
                            quality + repetition gate
                                     |
                              final response

Design rules taken from the spec:
  * Variation is produced by the model, driven by context and sampling -
    never by a stored list of alternative answers ("no response1..N").
  * Facts are the model's; only expression varies (17).
  * Retries are bounded (27) and a failure always degrades to the raw
    model reply instead of an error.
"""

from __future__ import annotations

import inspect
import logging
from typing import Any, Callable, Dict, List, Optional

from conversation import question_similarity as qs
from conversation import repetition_detector, response_planner, response_quality
from conversation import style_controller
from conversation.response_memory import response_memory
from conversation.response_planner import ResponsePlan

log = logging.getLogger("jarvis.conversation.response")

DIRECTIVE_HEADER = "RESPONSE DIRECTIVES (follow these for this reply only)"

# Debug trail (21).  Off by default; switch it on with
# "response_debug": true in config/settings.json.  Only decisions are
# recorded - never the conversation text itself.
DEBUG_LIMIT = 40


def debug_enabled() -> bool:
    """True when response debugging is switched on in settings.json."""
    try:
        from conversation.identity import identity

        return bool(identity.settings().get("response_debug", False))
    except Exception as error:  # pragma: no cover - defensive
        log.debug("response_debug flag unreadable: %s", error)
        return False

# Short acknowledgements for throwaway turns (23, 24).  These are not
# answers to questions - they are the conversational equivalent of a nod,
# and they rotate so the same word is not used twice in a row.
ACK_LINES = ("Got it.", "Alright.", "Okay.", "Noted.")
THANKS_LINES = ("Anytime.", "Sure.", "No problem.", "Happy to.")
PRAISE_LINES = ("Thanks.", "Glad it worked.", "Good to hear.")

# Natural acknowledgements for executed commands (30).  The action is
# already done; only the confirmation wording rotates.
ACTION_LINES = {
    "open": ("Opening {target}.", "{target} is opening.", "Launching {target}."),
    "close": ("Closing {target}.", "{target} is closed.", "Shutting {target} down."),
    "play": ("Playing {target}.", "{target} is playing.", "Starting {target}."),
    "search": ("Searching for {target}.", "Looking up {target}.", "On it - {target}."),
    "create": ("Created {target}.", "{target} is ready.", "Done - {target} created."),
    "generic": ("Done.", "Done - {target}.", "{target} is done."),
}

FAILURE_LINES = (
    "That didn't work - {target} failed.",
    "I couldn't do that: {target} failed.",
)


class ResponseGenerator:
    """Plans, generates, checks and records every substantive reply."""

    def __init__(self) -> None:
        self._rotations: Dict[str, int] = {}
        self.last_plan: Optional[ResponsePlan] = None
        self.last_report: Optional[response_quality.QualityReport] = None
        self.attempts = 0
        self.regenerations = 0
        self.debug_log: List[str] = []

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    def _rotate(self, key: str, options) -> str:
        """Next option in a small rotation - deliberately not random (19)."""
        if not options:
            return ""
        index = self._rotations.get(key, -1) + 1
        self._rotations[key] = index
        return options[index % len(options)]

    def _debug(self, line: str) -> None:
        """Record one decision, and print it when debugging is on (21)."""
        self.debug_log.append(line)
        if len(self.debug_log) > DEBUG_LIMIT:
            del self.debug_log[:-DEBUG_LIMIT]
        log.debug(line)
        if debug_enabled():
            print(line)

    @staticmethod
    def polish(text: str) -> str:
        """Remove reasoning traces and stock chatbot phrases (15)."""
        return repetition_detector.strip_cliches(text)

    def plan_for(
        self,
        message: str,
        understanding: Any = None,
        session_id: str = "",
        turn: int = 0,
        action: str = "",
    ) -> ResponsePlan:
        """Decision layer for this turn (26)."""
        return response_planner.plan(
            message,
            understanding=understanding,
            session_id=session_id,
            turn=turn,
            action=action,
        )

    def build_prompt(self, base_prompt: str, plan: ResponsePlan, attempt: int = 0) -> str:
        """Base prompt (personality + context + message) plus directives."""
        directives = style_controller.directives(plan, attempt)
        if not directives:
            return base_prompt
        block = "\n".join(f"- {line}" for line in directives)
        return f"{base_prompt.rstrip()}\n\n{DIRECTIVE_HEADER}\n{block}\n"

    # ------------------------------------------------------------------
    # command acknowledgements (30)
    # ------------------------------------------------------------------
    def acknowledge(self, action: str = "", target: str = "", success: bool = True) -> str:
        """Varied confirmation for an action that already ran."""
        target = (target or "").strip()
        action = (action or "").strip().lower()

        if not success:
            line = self._rotate("failure", FAILURE_LINES)
            return line.replace("{target}", target or "the action")

        options = ACTION_LINES.get(action, ACTION_LINES["generic"])
        line = self._rotate(f"action:{action}", options)
        if "{target}" in line and not target:
            line = self._rotate("action:generic", ACTION_LINES["generic"])
        return line.replace("{target}", target).strip()

    def minimal_reply(self, plan: ResponsePlan) -> str:
        """One short line for an acknowledgement turn (23, 24)."""
        if plan.subtype == "thanks":
            return self._rotate("thanks", THANKS_LINES)
        if plan.subtype == "praise":
            return self._rotate("praise", PRAISE_LINES)
        return self._rotate("ack", ACK_LINES)

    # ------------------------------------------------------------------
    # main entry point
    # ------------------------------------------------------------------
    def generate(
        self,
        message: str,
        ask: Optional[Callable[..., str]] = None,
        base_prompt: str = "",
        understanding: Any = None,
        session_id: str = "",
        turn: int = 0,
        action: str = "",
    ) -> str:
        """Produce the final reply for ``message``.

        ``ask`` is the AI Brain call, invoked as ``ask(prompt, options)``
        when it accepts options and ``ask(prompt)`` otherwise.  Passing the
        brain in keeps this layer independent of the provider.
        """
        plan = self.plan_for(
            message,
            understanding=understanding,
            session_id=session_id,
            turn=turn,
            action=action,
        )
        self.last_plan = plan
        self.last_report = None
        self.attempts = 0

        self._debug(
            "[CONVERSATION] intent=%s depth=%s structure=%s language=%s"
            % (
                plan.kind or "chat",
                plan.depth,
                plan.structure or "-",
                plan.language,
            )
        )
        if plan.repeat_count:
            self._debug(
                "[CONVERSATION] similar previous question detected "
                "(asked %d time(s) before)" % plan.repeat_count
            )

        # Throwaway turns never reach the model.
        if plan.minimal:
            reply = self.minimal_reply(plan)
            self.record(message, reply, plan, session_id)
            return reply

        if ask is None:
            return ""

        recent_answers = response_memory.recent_answers(limit=5)
        recent_openings = response_memory.recent_openings(limit=3)

        best = ""
        best_report: Optional[response_quality.QualityReport] = None

        for attempt in range(plan.max_retries + 1):
            prompt = self.build_prompt(base_prompt or message, plan, attempt)
            options = style_controller.parameters(plan, attempt)
            self.attempts += 1
            if attempt:
                self.regenerations += 1

            self._debug(
                "[AI] generating fresh response (attempt %d, temperature %.2f, "
                "top_p %.2f, seed %s)"
                % (
                    attempt + 1,
                    float(options.get("temperature", 0.0)),
                    float(options.get("top_p", 0.0)),
                    options.get("seed", "-"),
                )
            )

            raw = self._ask(ask, prompt, options)
            candidate = self.polish(raw)
            if not candidate:
                continue

            report = response_quality.check(
                candidate,
                plan,
                recent_answers=recent_answers,
                recent_openings=recent_openings,
                previous_answer=plan.previous_answer,
            )
            self.last_report = report

            if report.score:
                self._debug(
                    "[RESPONSE] similarity with recent replies: %.2f"
                    % report.score
                )
            if report.issues:
                self._debug(
                    "[RESPONSE] revising - %s" % ", ".join(report.issues)
                )

            if report.ok or report.unavailable:
                best = candidate
                best_report = report
                break

            # Keep the newest draft as the fallback and tell the model what
            # to fix on the next attempt.
            best = candidate
            best_report = report
            plan.issues = list(report.issues)
            plan.revision = report.directive

        if not best:
            return ""

        if best_report and not best_report.unavailable:
            self.record(message, best, plan, session_id)

        self._debug(
            "[RESPONSE] generated in %d attempt(s)" % max(1, self.attempts)
        )
        return best

    # ------------------------------------------------------------------
    def _ask(self, ask: Callable[..., str], prompt: str, options: Dict[str, Any]) -> str:
        """Call the AI Brain, with or without generation parameters."""
        try:
            if self._accepts_options(ask):
                return str(ask(prompt, options) or "")
            return str(ask(prompt) or "")
        except TypeError:
            try:
                return str(ask(prompt) or "")
            except Exception as error:  # pragma: no cover - defensive
                log.warning("model call failed: %s", error)
                return ""
        except Exception as error:  # pragma: no cover - defensive
            log.warning("model call failed: %s", error)
            return ""

    @staticmethod
    def _accepts_options(ask: Callable[..., str]) -> bool:
        try:
            signature = inspect.signature(ask)
        except (TypeError, ValueError):
            return False
        positional = 0
        for parameter in signature.parameters.values():
            if parameter.kind in (
                parameter.POSITIONAL_ONLY,
                parameter.POSITIONAL_OR_KEYWORD,
            ):
                positional += 1
            elif parameter.kind == parameter.VAR_POSITIONAL:
                return True
        return positional >= 2

    # ------------------------------------------------------------------
    def record(
        self,
        message: str,
        reply: str,
        plan: Optional[ResponsePlan] = None,
        session_id: str = "",
    ) -> None:
        """Remember what was said so the next answer can differ (4, 18).

        The turn number is passed through so the conversation engine's
        own write for the same turn is merged instead of counted twice.
        """
        try:
            response_memory.record(
                message,
                reply,
                session_id=session_id or getattr(plan, "session_id", ""),
                turn=int(getattr(plan, "turn", 0) or 0),
                structure=(plan.structure if plan else ""),
                topic=(plan.topic if plan else ""),
            )
        except Exception as error:  # pragma: no cover - defensive
            log.debug("response memory write failed: %s", error)

    # ------------------------------------------------------------------
    def info(self) -> Dict[str, Any]:
        """Diagnostics for the debug/status views."""
        return {
            "diversity": style_controller.level(),
            "attempts": self.attempts,
            "regenerations": self.regenerations,
            "remembered": response_memory.count(),
            "last_plan": self.last_plan.to_dict() if self.last_plan else {},
            "last_report": self.last_report.to_dict() if self.last_report else {},
        }


response_generator = ResponseGenerator()


def is_repeat_question(message: str, session_id: str = "") -> bool:
    """True when this information was already requested before (2)."""
    if not qs.is_question(message):
        return False
    return response_memory.times_asked(message, session_id) > 0


__all__ = [
    "ResponseGenerator",
    "response_generator",
    "is_repeat_question",
    "DIRECTIVE_HEADER",
]
