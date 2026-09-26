"""File tool for the brain's tool registry.

Adapter over the sandboxed :mod:`tools.file_tool` so commands cannot reach
outside the workspace.
"""

from __future__ import annotations

import re
from typing import Any, Dict

from tools.file_tool import SandboxError, file_tool as _backend

__all__ = ["FileTool", "file_tool"]

_READ = re.compile(r"\b(?:read|open|show|cat)\s+(?:the\s+)?file\s+(?P<path>\S+)",
                   re.IGNORECASE)
_WRITE = re.compile(
    r"\b(?:write|save|put)\s+(?P<content>.+?)\s+(?:to|into|in)\s+"
    r"(?:the\s+)?file\s+(?P<path>\S+)", re.IGNORECASE)
_LIST = re.compile(r"\b(?:list|show)\s+(?:the\s+)?(?:files|folder|directory)"
                   r"(?:\s+(?P<path>\S+))?", re.IGNORECASE)


class FileTool:
    name = "file"
    description = "Reads, writes and lists files inside the Jarvis workspace."

    def can_handle(self, command: Any) -> bool:
        text = str(command or "")
        return bool(_READ.search(text) or _WRITE.search(text) or _LIST.search(text))

    def execute(self, command: Any) -> Dict[str, Any]:
        text = str(command or "")

        try:
            match = _WRITE.search(text)
            if match:
                outcome = _backend.write(match.group("path"), match.group("content"))
                return {"success": outcome["success"],
                        "reply": "Wrote %s bytes to %s."
                                 % (outcome.get("bytes"), match.group("path"))}

            match = _READ.search(text)
            if match:
                outcome = _backend.read(match.group("path"))
                if not outcome["success"]:
                    return {"success": False, "reply": outcome["error"]}
                return {"success": True, "reply": outcome["content"][:2000]}

            match = _LIST.search(text)
            if match:
                outcome = _backend.list(match.group("path") or ".")
                if not outcome["success"]:
                    return {"success": False, "reply": outcome["error"]}
                names = ", ".join(entry["name"] for entry in outcome["entries"])
                return {"success": True, "reply": names or "(empty)"}

        except SandboxError as error:
            return {"success": False, "reply": str(error)}

        return {"success": False, "reply": "I couldn't parse that file command."}


file_tool = FileTool()
