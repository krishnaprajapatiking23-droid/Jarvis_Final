"""
Advanced Reasoning Engine
"""

from __future__ import annotations

import re
from typing import Any


class ReasoningEngine:

    DESTRUCTIVE_PATTERNS = [
        r"\bdelete\b",
        r"\bremove\b",
        r"\berase\b",
        r"\bformat\b",
        r"\buninstall\b",
        r"\bkill\b",
        r"\bshutdown\b",
        r"\brestart\b",
        r"\bwipe\b",
        r"\bdestroy\b",
    ]

    ACTION_PATTERNS = {
        "email": [
            r"\bsend\b.*\bemail\b",
            r"\bemail\b.*\bto\b",
        ],
        "open": [
            r"\bopen\b",
            r"\blaunch\b",
            r"\bstart\b",
        ],
        "build": [
            r"\bbuild\b",
            r"\bcreate\b",
            r"\bdevelop\b",
        ],
        "fix": [
            r"\bfix\b",
            r"\brepair\b",
            r"\bsolve\b",
        ],
        "learn": [
            r"\blearn\b",
            r"\bstudy\b",
            r"\bteach\s+me\b",
        ],
        "search": [
            r"\bsearch\b",
            r"\bfind\b",
            r"\blook\s+up\b",
        ],
        "delete": [
            r"\bdelete\b",
            r"\bremove\b",
            r"\berase\b",
            r"\bwipe\b",
        ],
        "shutdown": [
            r"\bshutdown\b",
            r"\brestart\b",
        ],
    }

    def _detect_actions(self, command: str) -> list[str]:
        actions = []

        for action, patterns in self.ACTION_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, command):
                    actions.append(action)
                    break

        return actions

    def _extract_goal_subject(
        self,
        command: str,
        action: str,
    ) -> str | None:

        patterns = {
            "build": [
                r"\b(?:create|build|develop)\s+(?:a|an|the)?\s*(.+)",
            ],
            "fix": [
                r"\b(?:fix|repair|solve)\s+(?:my|the|a|an)?\s*(.+)",
            ],
            "learn": [
                r"\b(?:learn|study)\s+(?:about|the)?\s*(.+)",
            ],
        }

        for pattern in patterns.get(action, []):
            match = re.search(pattern, command)

            if match:
                subject = match.group(1).strip()

                if action in {"build", "fix"}:
                    if not subject.startswith(("a ", "an ", "the ")):
                        subject = f"a {subject}"

                subject = re.split(
                    r"\b(?:and\s+then|then|after\s+that|afterwards)\b",
                    subject,
                    maxsplit=1,
                )[0].strip()

                if subject:
                    return subject

        return None

    def _determine_goal(
        self,
        command: str,
        actions: list[str],
    ) -> str:

        if not actions:
            return "Conversation"

        if len(actions) > 1:
            return "Execute multiple actions"

        action = actions[0]

        subject = self._extract_goal_subject(
            command,
            action,
        )

        if action == "build":
            if subject:
                return f"Create {subject}"
            return "Create a project"

        if action == "fix":
            if subject:
                return f"Fix {subject}"
            return "Fix a problem"

        if action == "learn":
            if subject:
                return f"Learn {subject}"
            return "Learn a topic"

        goals = {
            "email": "Send an email",
            "open": "Open an application",
            "search": "Search for information",
            "delete": "Delete data",
            "shutdown": "Control system power",
        }

        return goals.get(action, "Execute an action")

    def _calculate_risk(
        self,
        command: str,
        actions: list[str],
    ) -> str:

        if any(
            re.search(pattern, command)
            for pattern in self.DESTRUCTIVE_PATTERNS
        ):
            return "High"

        if "email" in actions or "build" in actions:
            return "Medium"

        if actions:
            return "Low"

        return "None"

    def _calculate_confidence(
        self,
        command: str,
        actions: list[str],
    ) -> int:

        if not command:
            return 0

        confidence = 50

        if actions:
            confidence += 25

        if len(actions) == 1:
            confidence += 10

        elif len(actions) > 1:
            confidence += 5

        words = command.split()

        if len(words) >= 2:
            confidence += 5

        if len(words) >= 4:
            confidence += 5

        if actions and self._determine_goal(command, actions) != "Execute an action":
            confidence += 5

        return min(confidence, 100)

    def _detect_order(
        self,
        command: str,
        actions: list[str],
    ) -> list[str]:

        if len(actions) <= 1:
            return actions

        ordered = []

        parts = re.split(
            r"\b(?:and\s+then|then|after\s+that|afterwards)\b",
            command,
        )

        for part in parts:
            for action in actions:
                patterns = self.ACTION_PATTERNS[action]

                if any(
                    re.search(pattern, part)
                    for pattern in patterns
                ):
                    if action not in ordered:
                        ordered.append(action)

        for action in actions:
            if action not in ordered:
                ordered.append(action)

        return ordered

    def _build_steps(
        self,
        ordered_actions: list[str],
    ) -> list[dict[str, Any]]:

        steps = []

        for index, action in enumerate(ordered_actions, start=1):
            steps.append(
                {
                    "order": index,
                    "action": action,
                    "status": "pending",
                }
            )

        return steps

    def analyze(self, command: str) -> dict[str, Any]:

        command = str(command).strip()
        normalized = command.lower()

        actions = self._detect_actions(normalized)

        ordered_actions = self._detect_order(
            normalized,
            actions,
        )

        steps = self._build_steps(
            ordered_actions,
        )

        risk = self._calculate_risk(
            normalized,
            actions,
        )

        confidence = self._calculate_confidence(
            normalized,
            actions,
        )

        goal = self._determine_goal(
            command,
            actions,
        )

        reasoning = []

        if actions:
            reasoning.append(
                f"Detected action(s): {', '.join(ordered_actions)}."
            )
        else:
            reasoning.append(
                "No executable action detected; treat as conversation."
            )

        if len(ordered_actions) > 1:
            reasoning.append(
                "Multiple actions detected; preserve their order."
            )

        reasoning.append(
            f"Risk level assessed as {risk}."
        )

        reasoning.append(
            f"Confidence assessed at {confidence}%."
        )

        if risk == "High":
            reasoning.append(
                "Action may be destructive and should require verification."
            )

        return {
            "goal": goal,
            "actions": actions,
            "ordered_actions": ordered_actions,
            "steps": steps,
            "risk": risk,
            "confidence": confidence,
            "reasoning": reasoning,
            "requires_verification": risk == "High",
        }


reasoning_engine = ReasoningEngine()