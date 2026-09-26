"""Date and time tool.

Answers "what time is it", "what is today's date", "what day is it",
"how many days until <date>" without any model call.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Dict, Optional

__all__ = ["DateTimeTool", "datetime_tool", "answer"]

_TIME_Q = re.compile(r"\b(what(?:'s| is|s)?\s+the\s+time|what\s+time\s+is\s+it|"
                     r"current\s+time|time\s+now)\b", re.IGNORECASE)
_DATE_Q = re.compile(r"\b(what(?:'s| is|s)?\s+(?:the\s+)?date|today's\s+date|"
                     r"what\s+is\s+today|current\s+date)\b", re.IGNORECASE)
_DAY_Q = re.compile(r"\b(what\s+day\s+is\s+it|what\s+day\s+is\s+today|"
                    r"which\s+day\s+is\s+it)\b", re.IGNORECASE)
_UNTIL_Q = re.compile(r"\bhow\s+(?:many\s+days|long)\s+(?:until|till|to)\s+(?P<target>.+)$",
                      re.IGNORECASE)


class DateTimeTool:
    """Answers clock/calendar questions from the system clock."""

    name = "datetime"
    description = "Current time, date, weekday and day countdowns."

    def can_handle(self, command: Any) -> bool:
        text = str(command or "")
        return bool(_TIME_Q.search(text) or _DATE_Q.search(text)
                    or _DAY_Q.search(text) or _UNTIL_Q.search(text))

    def execute(self, command: Any, now: Optional[datetime] = None) -> Dict[str, Any]:
        text = str(command or "")
        now = now or datetime.now()

        if _TIME_Q.search(text):
            return {"success": True, "reply": "It's %s." % now.strftime("%H:%M")}

        if _DAY_Q.search(text):
            return {"success": True,
                    "reply": "Today is %s." % now.strftime("%A")}

        if _DATE_Q.search(text):
            return {"success": True,
                    "reply": "Today is %s." % now.strftime("%A %d %B %Y")}

        match = _UNTIL_Q.search(text)
        if match:
            from brains_v2.nl_time import parse_time

            target = parse_time(match.group("target"), now=now)
            if not target:
                return {"success": False,
                        "reply": "I couldn't work out that date."}
            days = (target.date() - now.date()).days
            if days == 0:
                return {"success": True, "reply": "That's today."}
            if days == 1:
                return {"success": True, "reply": "That's tomorrow."}
            return {"success": True, "reply": "%d days from now." % days}

        return {"success": False, "reply": "I can't answer that from the clock."}


datetime_tool = DateTimeTool()


def answer(command: Any) -> Optional[str]:
    """Convenience helper returning just the sentence, or None."""
    if not datetime_tool.can_handle(command):
        return None
    return datetime_tool.execute(command).get("reply")
