"""Offline reasoning helpers (roadmap sections 1 and 41).

Decomposes a request into premises, constraints and unknowns and produces an
explainable chain of steps -- without needing a language model, so reasoning
still works when the model backend is offline.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List

__all__ = ["Reasoner", "reasoner", "analyse"]

_CONSTRAINT = re.compile(
    r"\b(?:without|must not|don'?t|do not|never|avoid|except|unless|"
    r"only if|no more than|at most|before|after|within)\b[^,.;]*",
    re.IGNORECASE,
)
_GOAL = re.compile(
    r"\b(?:i want to|i need to|please|can you|could you|help me)\s+(?P<goal>[^,.;]+)",
    re.IGNORECASE,
)
_QUESTION = re.compile(r"\b(who|what|when|where|why|how|which)\b", re.IGNORECASE)
_CAUSAL = re.compile(r"\b(because|since|so that|therefore|as a result|due to)\b",
                     re.IGNORECASE)
_CONDITION = re.compile(r"\b(if|when|whenever|in case)\b[^,.;]*", re.IGNORECASE)

DOMAINS = {
    "coding": ("code", "python", "function", "bug", "error", "script",
               "repository", "test", "compile"),
    "research": ("research", "find out", "compare", "sources", "evidence",
                 "study", "paper"),
    "automation": ("open", "close", "launch", "click", "type", "screenshot",
                   "window", "file"),
    "memory": ("remember", "forget", "recall", "my name", "my favourite"),
    "planning": ("plan", "schedule", "organise", "organize", "roadmap", "steps"),
}


class Reasoner:
    """Structural analysis of a request."""

    def domain(self, text: str) -> str:
        lowered = str(text or "").lower()
        best, score = "general", 0
        for name, markers in DOMAINS.items():
            hits = sum(1 for marker in markers if marker in lowered)
            if hits > score:
                best, score = name, hits
        return best

    def constraints(self, text: str) -> List[str]:
        return [match.group(0).strip()
                for match in _CONSTRAINT.finditer(str(text or ""))][:8]

    def conditions(self, text: str) -> List[str]:
        return [match.group(0).strip()
                for match in _CONDITION.finditer(str(text or ""))][:8]

    def goal(self, text: str) -> str:
        match = _GOAL.search(str(text or ""))
        if match:
            return match.group("goal").strip()
        return str(text or "").strip()

    def unknowns(self, text: str) -> List[str]:
        found = []
        lowered = str(text or "").lower()
        if _QUESTION.search(lowered):
            found.append("the answer to the question asked")
        if re.search(r"\b(it|this|that|they|them)\b", lowered):
            found.append("what the pronouns refer to")
        if re.search(r"\b(soon|later|sometime|a while)\b", lowered):
            found.append("the exact time meant")
        return found

    def steps(self, text: str) -> List[str]:
        goal = self.goal(text)
        plan = ["Understand the request: %s" % goal]
        constraints = self.constraints(text)
        if constraints:
            plan.append("Respect %d constraint(s): %s"
                        % (len(constraints), "; ".join(constraints)))
        unknowns = self.unknowns(text)
        if unknowns:
            plan.append("Resolve unknowns: %s" % ", ".join(unknowns))
        plan.append("Choose the manager for the %s domain" % self.domain(text))
        plan.append("Execute, then verify the result before answering")
        return plan

    def analyse(self, text: str) -> Dict[str, Any]:
        return {
            "goal": self.goal(text),
            "domain": self.domain(text),
            "constraints": self.constraints(text),
            "conditions": self.conditions(text),
            "unknowns": self.unknowns(text),
            "causal": bool(_CAUSAL.search(str(text or ""))),
            "is_question": bool(_QUESTION.search(str(text or ""))),
            "steps": self.steps(text),
        }


reasoner = Reasoner()


def analyse(text: str) -> Dict[str, Any]:
    return reasoner.analyse(text)
