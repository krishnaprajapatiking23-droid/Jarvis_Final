"""
==========================================
JARVIS PRO
Clarification Manager  (feature 3.25)
==========================================

Asks the smallest useful question, then remembers what it was waiting for so
the user's short answer can be merged back into the original request.

    "Open it."                 -> "Which one do you mean: Chrome or Notepad?"
    "Chrome"                   -> executes "Open Chrome"

Conversation state is preserved across the clarification: the pending action
keeps the original text, the resolved action word and the offered options.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from conversation.conversation_state import ConversationState

YES = {"yes", "yeah", "yep", "yup", "sure", "ok", "okay", "correct", "right", "haan"}
NO = {"no", "nope", "nah", "not really", "negative", "nahi"}
CANCEL = {"never mind", "nevermind", "forget it", "cancel", "skip", "leave it"}


class ClarificationManager:
    """Builds minimal clarification questions and interprets the answers."""

    # ------------------------------------------------------------------
    def question_for(self, report: Dict[str, Any], text: str) -> str:
        """Smallest question that resolves ``report``."""
        missing = report.get("missing") or []

        if report.get("reason") == "missing_parameters" and missing:
            action = report.get("action") or "do that"

            if missing == ["file"]:
                return f"Which file would you like me to {action}?"

            if "file" in missing and "recipient" in missing:
                return (
                    f"Which file would you like me to {action}, "
                    "and to whom?"
                )

            if missing == ["recipient"]:
                return f"Who should I {action} it to?"

            return f"I need a bit more detail before I {action} that."

        options = report.get("options") or []
        names = [str(option.get("name", "")).strip() for option in options]
        names = [name for name in names if name]

        if len(names) >= 2:
            listed = " or ".join([", ".join(names[:-1]), names[-1]])
            return f"Which one do you mean: {listed}?"

        action = report.get("action") or ""
        if report.get("reason") == "no_candidate":
            if action:
                return f"What should I {action}?"
            return "What are you referring to?"

        if names:
            return f"Do you mean {names[0]}?"

        return "What are you referring to?"

    # ------------------------------------------------------------------
    def ask(
        self,
        state: ConversationState,
        report: Dict[str, Any],
        text: str,
    ) -> str:
        """Store the pending action on ``state`` and return the question."""
        question = self.question_for(report, text)
        state.ask(
            question,
            {
                "type": "clarification",
                "original": text,
                "action": report.get("action", ""),
                "reference": report.get("reference", ""),
                "options": report.get("options") or [],
                "missing": report.get("missing") or [],
            },
        )
        return question

    # ------------------------------------------------------------------
    def resolve_answer(
        self, state: ConversationState, answer: str
    ) -> Optional[Dict[str, Any]]:
        """Interpret ``answer`` against the pending clarification.

        Returns None when nothing was pending.  Otherwise::

            {
                "status": "resolved" | "cancelled" | "unclear",
                "command": "open chrome",     # only when resolved
                "choice": "Chrome",
            }
        """
        pending = state.pending_action
        if not pending or pending.get("type") != "clarification":
            return None

        lowered = (answer or "").strip().lower().rstrip(".!?")
        if not lowered:
            return {"status": "unclear"}

        if lowered in CANCEL or any(phrase in lowered for phrase in CANCEL):
            state.clear_pending()
            return {"status": "cancelled"}

        options: List[Dict[str, Any]] = pending.get("options") or []
        original: str = pending.get("original", "")
        reference: str = pending.get("reference", "")
        action: str = pending.get("action", "")

        choice: Optional[str] = None

        for option in options:
            name = str(option.get("name", "")).strip()
            if not name:
                continue
            if re.search(rf"\b{re.escape(name.lower())}\b", lowered):
                choice = name
                break

        if choice is None and len(options) == 1 and lowered in YES:
            choice = str(options[0].get("name", "")).strip()

        if choice is None and lowered in NO:
            state.clear_pending()
            return {"status": "cancelled"}

        if choice is None and len(lowered.split()) <= 4 and lowered not in YES:
            # Treat a short free-form reply as the answer itself.
            choice = answer.strip().rstrip(".!?")

        if not choice:
            return {"status": "unclear"}

        if reference and original:
            command = re.sub(
                rf"\b{re.escape(reference)}\b",
                choice,
                original,
                count=1,
                flags=re.IGNORECASE,
            )
        elif action:
            command = f"{action} {choice}"
        else:
            command = choice

        state.clear_pending()
        return {"status": "resolved", "command": command, "choice": choice}


clarification_manager = ClarificationManager()

__all__ = ["ClarificationManager", "clarification_manager"]
