"""Coding agent: reads, checks and writes code in the sandboxed workspace."""

from __future__ import annotations

import re
from typing import Any, Dict

from brains_v2.agents.base import Agent, AgentResult

__all__ = ["CodingAgent", "coding_agent"]

TRIGGERS = re.compile(r"\b(code|python|function|class|bug|refactor|test|script|syntax)\b", re.IGNORECASE)


class CodingAgent(Agent):
    name = "coding"
    capability = "coding"
    description = "Coding agent: reads, checks and writes code in the sandboxed workspace."

    def can_handle(self, goal: str) -> bool:
        return bool(TRIGGERS.search(str(goal or "")))

    def act(self, step: Dict[str, Any], goal: str,
            context: Dict[str, Any]) -> Dict[str, Any]:
        from skills.coding import coding_skill
        from tools.file_tool import SandboxError, file_tool

        match = re.search(r"([\w./-]+\.py)", str(goal or ""))
        if not match:
            return AgentResult(False, "Name the .py file you want me to look at.")

        try:
            read = file_tool.read(match.group(1))
        except SandboxError as error:
            return AgentResult(False, str(error))

        if not read.get("success"):
            return AgentResult(False, read.get("error", "could not read the file"))

        report = coding_skill.execute(read["content"])
        return AgentResult(bool(report.get("success")), report.get("reply", ""),
                           report=report)

coding_agent = CodingAgent()
