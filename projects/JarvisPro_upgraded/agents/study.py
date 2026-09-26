"""Study agent: turns material into a revision plan and quiz prompts."""

from __future__ import annotations

import re
from typing import Any, Dict, List

from brains_v2.agents.base import Agent, AgentResult

__all__ = ["StudyAgent", "study_agent"]

TRIGGERS = re.compile(
    r"\b(study|revise|revision|learn|exam|quiz|flashcard|memorise|memorize)\b",
    re.IGNORECASE,
)
_SENTENCE = re.compile(r"(?<=[.!?])\s+")

# Spaced-repetition intervals in days.
INTERVALS = (1, 3, 7, 14, 30)


class StudyAgent(Agent):
    name = "study"
    capability = "study"
    description = "Builds a revision schedule and questions from material."

    def can_handle(self, goal: str) -> bool:
        return bool(TRIGGERS.search(str(goal or "")))

    def key_points(self, material: str, limit: int = 10) -> List[str]:
        sentences = [s.strip() for s in _SENTENCE.split(str(material or ""))
                     if len(s.strip()) > 30]
        sentences.sort(key=len, reverse=True)
        return sentences[:limit]

    def questions(self, material: str) -> List[str]:
        asked: List[str] = []
        for point in self.key_points(material):
            match = re.match(r"(?P<subject>[^,]{3,60}?)\s+(?:is|are|was|were)\s+",
                             point, re.IGNORECASE)
            if match:
                asked.append("What is %s?" % match.group("subject").strip())
            else:
                asked.append("Explain: %s" % point[:80])
        return asked[:10]

    def schedule(self, topic: str) -> List[Dict[str, Any]]:
        return [{"session": index, "in_days": days,
                 "focus": "%s -- review %d" % (topic, index)}
                for index, days in enumerate(INTERVALS, start=1)]

    def act(self, step: Dict[str, Any], goal: str,
            context: Dict[str, Any]) -> Dict[str, Any]:
        material = str(context.get("material") or goal)
        topic = re.sub(r"^\s*(?:help me\s+)?(?:study|revise|learn)\s+", "",
                       str(goal or ""), flags=re.IGNORECASE).strip(" ?.")

        plan = self.schedule(topic or "the material")
        asked = self.questions(material)

        lines = ["Revision plan for %s:" % (topic or "your material")]
        lines += ["  +%d day(s): %s" % (item["in_days"], item["focus"])
                  for item in plan]
        if asked:
            lines.append("Practice questions:")
            lines += ["  - %s" % question for question in asked[:5]]

        return AgentResult(True, "\n".join(lines), plan=plan, questions=asked)


study_agent = StudyAgent()
