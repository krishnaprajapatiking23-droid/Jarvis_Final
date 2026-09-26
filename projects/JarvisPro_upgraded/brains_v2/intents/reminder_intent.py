"""Reminder intent detection.

BUG FIX (three defects):

* The add-pattern was ``remind me [tomorrow] at <H>[:MM] [am|pm] to <task>``
  and used ``re.match``, so the time had to come *before* the task.
  ``"remind me to call mom at 5pm"`` -- the ordinary way to say it -- never
  matched.
* Listing required the exact string ``"show reminders"``. ``"show my
  reminders"`` fell through.
* Anything else containing the word "remind" ended at a catch-all
  ``return "Please include a reminder time."`` in the manager module, so
  ``"show my reminders"`` literally answered "Please include a reminder time."

Time parsing is now delegated to :mod:`brains_v2.nl_time`, so any phrasing it
understands ("in 20 minutes", "tonight", "next monday", "on 5 March") works
here too.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Dict, Optional

from brains_v2.nl_time import parse_time, strip_time_phrase

__all__ = ["detect"]

_SHOW = re.compile(
    r"^(?:please\s+)?(?:show|list|display|read|get|what\s+are|whats|what's|"
    r"give\s+me|do\s+i\s+have)\s*(?:me\s+)?"
    r"(?:a|an|the|my|all|any|of)*\s*"
    r"(?:reminders?|reminder\s+list)\s*(?:set|pending|left)?\s*(?:please)?[?.!]*$",
    re.IGNORECASE,
)

_MUTATE = re.compile(
    r"^(?:please\s+)?(?P<op>cancel|delete|remove|complete|finish|done\s+with)\s+"
    r"(?:a|an|the|my)*\s*reminder\s*(?:number|#)?\s*(?P<token>\S+)[?.!]*$",
    re.IGNORECASE,
)

_UPDATE = re.compile(
    r"^(?:please\s+)?(?:update|edit|change)\s+(?:a|an|the|my)*\s*"
    r"reminder\s*(?:number|#)?\s*(?P<token>\S+)\s+(?P<rest>.+)$",
    re.IGNORECASE,
)

_SNOOZE = re.compile(
    r"^(?:please\s+)?snooze\s+(?:a|an|the|my)*\s*reminder\s*"
    r"(?:number|#)?\s*(?P<token>\S+)(?:\s+(?P<rest>.+))?$",
    re.IGNORECASE,
)

_ADD = re.compile(
    r"^(?:please\s+)?"
    r"(?:remind\s+me\s+(?:to\s+|that\s+|about\s+)?|"
    r"set\s+(?:a|an|the)?\s*reminder\s+(?:to\s+|for\s+|about\s+)?|"
    r"create\s+(?:a|an|the)?\s*reminder\s+(?:to\s+|for\s+|about\s+)?|"
    r"add\s+(?:a|an|the)?\s*reminder\s+(?:to\s+|for\s+|about\s+)?)"
    r"(?P<body>.+)$",
    re.IGNORECASE | re.DOTALL,
)

_OPS = {
    "cancel": "cancel", "delete": "cancel", "remove": "cancel",
    "complete": "complete", "finish": "complete", "done with": "complete",
}


def detect(command: Any, now: Optional[datetime] = None) -> Optional[Dict[str, Any]]:
    """Classify ``command`` as a reminder operation, or return ``None``."""
    text = " ".join(str(command or "").split())
    if not text:
        return None

    lowered = text.lower()
    if "remind" not in lowered:
        return None

    if _SHOW.match(text):
        return {"type": "show_reminders"}

    match = _MUTATE.match(text)
    if match:
        operation = _OPS.get(match.group("op").lower().strip(), "cancel")
        return {"type": operation, "token": match.group("token").strip(".,")}

    match = _UPDATE.match(text)
    if match:
        rest = match.group("rest").strip()
        return {
            "type": "update",
            "token": match.group("token").strip(".,"),
            "title": strip_time_phrase(rest) or rest,
            "when": rest,
        }

    match = _SNOOZE.match(text)
    if match:
        return {
            "type": "snooze",
            "token": match.group("token").strip(".,"),
            "when": match.group("rest") or "in 10 minutes",
        }

    match = _ADD.match(text)
    if match:
        body = match.group("body").strip()
        due = parse_time(body, now=now)
        title = strip_time_phrase(body).strip(" ,.-")
        # "remind me to call mom at 5pm" -> title "call mom"
        title = re.sub(r"^(?:to|that|about)\s+", "", title, flags=re.IGNORECASE)
        if not title:
            title = body
        result: Dict[str, Any] = {"type": "add_reminder", "title": title}
        if due:
            result["time"] = due
            result["has_time"] = True
        else:
            result["has_time"] = False
        return result

    return None
