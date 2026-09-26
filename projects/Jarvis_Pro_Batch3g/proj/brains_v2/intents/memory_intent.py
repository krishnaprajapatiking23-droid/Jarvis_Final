"""
==========================================
JARVIS PRO
Memory intent detection
==========================================

The old detector matched substrings anywhere in the message:

    "i want to"    -> goal
    "my favorite"  -> preference
    startswith("remember ") -> remember the *whole rest of the message*

So "Remember that my project is called JARVIS. What is my project called?"
stored the question as part of the fact, and
"My favorite language is Python. What did I just tell you?" became a memory
write instead of a history question.

It now uses ``conversation.request_splitter`` to separate the memory
instruction, the fact and the question, and it refuses to claim a message
whenever the user actually asked something or left the sentence unfinished.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Optional

from conversation.request_splitter import parse_fact, split

GOAL = re.compile(
    r"^(?:i|we)\s+(?:want|need|would like|plan|intend)\s+to\s+(?P<goal>.+)$",
    re.IGNORECASE,
)
PREFERENCE = re.compile(
    r"^(?:my|our)\s+(?:favorite|favourite|preferred)\s+(?P<what>.+)$",
    re.IGNORECASE,
)
NAME = re.compile(r"^(?:my name is|i am called|call me)\s+(?P<name>.+)$", re.IGNORECASE)
AGE = re.compile(r"^i am\s+(?P<age>\d{1,3})(?:\s+years?\s+old)?$", re.IGNORECASE)
FRIEND = re.compile(r"^my friend is\s+(?P<name>.+)$", re.IGNORECASE)

RECALL_GOALS = ("what are my goals", "what is my goal", "what were my goals")
RECALL_NAME = ("what is my name", "what's my name", "do you know my name")
RECALL_AGE = ("how old am i", "what is my age")
RECALL_FRIENDS = ("who are my friends", "list my friends")


def _clean(sentence: str) -> str:
    return (sentence or "").strip().rstrip(".!;")


def detect(command: str) -> Optional[Dict[str, Any]]:
    """Classify ``command`` as a memory operation, or return None.

    Returns dicts of the shape used by
    ``brains_v2/controllers/memory_controller.py``:
    ``{"type": "remember_fact", "text": "my project is called JARVIS"}``.
    A ``question`` key is added when the same message also asked something,
    so the caller can answer it instead of swallowing it.
    """

    text = (command or "").strip()

    if not text:
        return None

    request = split(text)
    lowered = text.lower().rstrip("?.! ")

    # ---------- pure recall questions ----------
    if lowered.startswith(RECALL_GOALS):
        return {"type": "recall_goals"}

    if lowered.startswith(RECALL_NAME):
        return {"type": "get_name"}

    if lowered.startswith(RECALL_AGE):
        return {"type": "get_age"}

    if lowered.startswith(RECALL_FRIENDS):
        return {"type": "list_people"}

    # ---------- explicit "remember ..." instructions ----------
    if request.has_memory:
        fact = _clean(request.memory[0])

        if not fact:
            return None

        return {
            "type": "remember_fact",
            "text": fact,
            "question": request.question,
            "fact": parse_fact(fact),
        }

    # Never treat an unfinished sentence as something to store.
    if request.incomplete:
        return None

    # A message that asks something is conversation, not a memory write,
    # unless it also carried an explicit "remember" instruction (above).
    if request.has_question:
        return None

    if len(request.statements) != 1:
        return None

    statement = _clean(request.statements[0])

    match = NAME.match(statement)
    if match:
        return {"type": "set_name", "value": match.group("name").strip()}

    match = AGE.match(statement)
    if match:
        return {"type": "set_age", "value": match.group("age").strip()}

    match = FRIEND.match(statement)
    if match:
        return {"type": "add_person", "value": match.group("name").strip()}

    match = PREFERENCE.match(statement)
    if match:
        return {"type": "preference", "text": statement}

    match = GOAL.match(statement)
    if match:
        return {"type": "goal", "text": statement}

    return None


__all__ = ["detect"]
