"""Note intent detection.

BUG FIX: the previous detector matched four hard-coded literal prefixes --
``"note "``, ``"add note "``, and the exact strings ``"show notes"`` and
``"clear notes"``. So ``"add note buy milk"`` worked but ``"add a note buy
milk"`` and ``"show my notes"`` both fell through to the LLM. Detection is now
pattern-based and tolerant of the filler words people actually use.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Optional

__all__ = ["detect"]

_FILLER = r"(?:a|an|the|my|all|new|quick|this|of)\s+"

_ADD = re.compile(
    r"^(?:please\s+)?(?:add|make|create|save|write|take|jot\s+down|note)\s*"
    r"(?:" + _FILLER + r")*"
    r"(?:note|memo|reminder\s+note)?\s*"
    r"(?:that|saying|about|:|-)?\s*(?P<content>.+)$",
    re.IGNORECASE | re.DOTALL,
)
_ADD_BARE = re.compile(r"^note\s+(?P<content>.+)$", re.IGNORECASE | re.DOTALL)
_JOT = re.compile(r"^(?:please\s+)?jot\s+down\s+(?P<content>.+)$",
                  re.IGNORECASE | re.DOTALL)

_SHOW = re.compile(
    r"^(?:please\s+)?(?:show|list|display|read|get|what\s+are|whats|what's|"
    r"give\s+me)\s*(?:me\s+)?(?:" + _FILLER + r")*"
    r"(?:notes|note\s+list|all\s+notes)\s*(?:please)?[?.!]*$",
    re.IGNORECASE,
)

_READ = re.compile(
    r"^(?:please\s+)?(?:read|show|open|get)\s+(?:" + _FILLER + r")*"
    r"note\s*(?:number|#)?\s*(?P<index>\d+)[?.!]*$",
    re.IGNORECASE,
)

_DELETE = re.compile(
    r"^(?:please\s+)?(?:delete|remove|drop|erase)\s+(?:" + _FILLER + r")*"
    r"note\s*(?:number|#)?\s*(?P<index>\d+)[?.!]*$",
    re.IGNORECASE,
)

_CLEAR = re.compile(
    r"^(?:please\s+)?(?:clear|delete|remove|erase|wipe)\s+"
    r"(?:all\s+|every\s+|my\s+)*notes?[?.!]*$",
    re.IGNORECASE,
)

# Things that merely mention the word "note" but are not note commands.
_NOT_A_NOTE = re.compile(
    r"\b(note that you|note the following|noteworthy|take note of how)\b",
    re.IGNORECASE,
)


def detect(command: Any) -> Optional[Dict[str, Any]]:
    """Classify ``command`` as a note operation, or return ``None``."""
    text = " ".join(str(command or "").split())
    if not text or _NOT_A_NOTE.search(text):
        return None

    lowered = text.lower()
    # "jot down X" is a note command even though it never says "note".
    if "note" not in lowered and not _JOT.match(text):
        return None

    if _CLEAR.match(text):
        return {"type": "clear_notes"}

    match = _DELETE.match(text)
    if match:
        return {"type": "delete_note", "index": int(match.group("index"))}

    match = _READ.match(text)
    if match:
        return {"type": "read_note", "index": int(match.group("index"))}

    if _SHOW.match(text):
        return {"type": "show_notes"}

    match = _JOT.match(text)
    if match:
        content = match.group("content").strip(" :-,")
        if content:
            return {"type": "add_note", "content": content}

    match = _ADD.match(text)
    if match:
        content = match.group("content").strip(" :-,")
        if content:
            return {"type": "add_note", "content": content}

    match = _ADD_BARE.match(text)
    if match:
        content = match.group("content").strip(" :-,")
        if content:
            return {"type": "add_note", "content": content}

    return None
