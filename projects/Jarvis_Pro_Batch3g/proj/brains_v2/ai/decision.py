"""
Context-Aware and Autonomous Decision System
with Decision Explanation and Human Approval Checkpoints
"""

from __future__ import annotations

from typing import Any

from brains_v2.tools.manager import process as tool_manager


class ContextAwareDecision:

    def __init__(self):
        self.context: dict[str, Any] = {}
        self.pending_approvals: list[dict[str, Any]] = []

    def update_context(
        self,
        data: dict[str, Any],
    ) -> None:

        if "command" in data:
            self.context["last_command"] = data["command"]

        if "intent" in data:
            self.context["last_intent"] = data["intent"]

        if "goal" in data:
            self.context["last_goal"] = data["goal"]

        if "confidence" in data:
            self.context["confidence"] = data["confidence"]

        if "risk" in data:
            self.context["risk"] = data["risk"]

        if "situation" in data:
            self.context["situation"] = data["situation"]

    def get_context(self) -> dict[str, Any]:
        return dict(self.context)

    def enrich(
        self,
        data: dict[str, Any],
    ) -> dict[str, Any]:

        enriched = dict(data)

        context = self.get_context()

        if context:
            enriched["context"] = context

        return enriched

    def autonomous_decision(
        self,
        data: dict[str, Any],
    ) -> dict[str, Any]:

        confidence = data.get("confidence", 100)
        risk = data.get("risk", "None")

        intent = data.get("intent", {})
        intent_name = intent.get("intent")

        if confidence < 60:
            return {
                "action": "ask_clarification",
                "reason": "Confidence is too low",
            }

        if risk == "High":
            return {
                "action": "request_verification",
                "reason": "The requested action has high risk",
            }

        intent_actions = {
            "open_app": "open_app",
            "open_website": "open_website",
            "remember": "remember",
            "recall": "recall",
            "note": "note",
            "reminder": "reminder",
            "search_web": "search_web",
            "search_file": "search_file",
            "scan_project": "scan_project",
            "analyze_project": "analyze_project",
            "debug_project": "debug_project",
            "conversation": "respond",
        }

        if intent_name in intent_actions:
            return {
                "action": "execute",
                "target": intent_actions[intent_name],
                "reason": "Known intent with sufficient confidence",
            }

        return {
            "action": "ask_clarification",
            "reason": "No suitable action was identified",
        }

    def create_approval_checkpoint(
        self,
        data: dict[str, Any],
    ) -> dict[str, Any]:

        checkpoint = {
            "command": data.get("command", ""),
            "risk": data.get("risk", "High"),
            "confidence": data.get("confidence", 0),
            "intent": data.get("intent", {}),
            "status": "pending",
        }

        self.pending_approvals.append(checkpoint)

        return checkpoint

    def approve(
        self,
        index: int = 0,
    ) -> dict[str, Any] | None:

        if not (
            0 <= index < len(self.pending_approvals)
        ):
            return None

        checkpoint = self.pending_approvals[index]

        if checkpoint["status"] != "pending":
            return checkpoint

        checkpoint["status"] = "approved"

        return checkpoint

    def reject(
        self,
        index: int = 0,
    ) -> dict[str, Any] | None:

        if not (
            0 <= index < len(self.pending_approvals)
        ):
            return None

        checkpoint = self.pending_approvals[index]

        if checkpoint["status"] != "pending":
            return checkpoint

        checkpoint["status"] = "rejected"

        return checkpoint

    def pending_approval_count(self) -> int:
        return sum(
            checkpoint["status"] == "pending"
            for checkpoint in self.pending_approvals
        )

    def explain_decision(
        self,
        data: dict[str, Any],
    ) -> dict[str, Any]:

        decision = data.get(
            "autonomous_decision",
            {},
        )

        action = decision.get(
            "action",
            "unknown",
        )

        confidence = data.get(
            "confidence",
            self.context.get("confidence"),
        )

        risk = data.get(
            "risk",
            self.context.get("risk"),
        )

        intent = data.get(
            "intent",
            self.context.get(
                "last_intent",
                {},
            ),
        )

        intent_name = (
            intent.get("intent")
            if isinstance(intent, dict)
            else str(intent)
        )

        return {
            "decision": action,
            "target": decision.get("target"),
            "intent": intent_name,
            "confidence": confidence,
            "risk": risk,
            "reason": decision.get(
                "reason",
                "No explanation available",
            ),
        }

    def decide(
        self,
        data: dict[str, Any],
    ) -> dict[str, Any]:

        self.update_context(data)

        decision = self.autonomous_decision(data)

        if decision["action"] == "request_verification":

            checkpoint = (
                self.create_approval_checkpoint(data)
            )

            enriched = self.enrich(data)

            enriched["autonomous_decision"] = decision

            enriched["approval_checkpoint"] = (
                checkpoint
            )

            enriched["decision_explanation"] = (
                self.explain_decision(enriched)
            )

            return enriched

        intent = data.get("intent", {})
        intent_name = intent.get("intent")

        if intent_name in [
            "scan_project",
            "analyze_project",
            "debug_project",
        ]:

            if decision["action"] == "execute":

                result = tool_manager(
                    data.get("command", "")
                )

                if result:

                    self.update_context(result)

                    if isinstance(result, dict):
                        enriched = self.enrich(result)
                    else:
                        enriched = self.enrich(data)

                else:
                    enriched = self.enrich(data)

            else:
                enriched = self.enrich(data)

        else:
            enriched = self.enrich(data)

        enriched["autonomous_decision"] = decision

        enriched["decision_explanation"] = (
            self.explain_decision(enriched)
        )

        return enriched


context_decision = ContextAwareDecision()


def decision_step(
    data: dict[str, Any],
):

    return context_decision.decide(data)