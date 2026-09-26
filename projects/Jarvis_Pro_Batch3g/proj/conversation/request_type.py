"""
==========================================
JARVIS PRO
Request type - information request vs action command
==========================================

The router used to decide "this is automation" from keywords alone, so
any sentence that merely *mentioned* an app name was executed:

    "Tell me about Notepad."      -> opened Notepad
    "Send the file to my friend." -> "Opening Application."

This module answers one question for the router and the brain manager:
is the user *asking about* something, or *telling JARVIS to do* something?
It looks at the grammatical role of the first clause - the verb in
command position - instead of scanning the whole sentence for nouns.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Request kinds
CONVERSATION = "conversation"
QUESTION = "question"
MEMORY = "memory"
ACTION = "action"
AUTOMATION = "automation"
SYSTEM = "system"

# Verbs that really do something to the machine.
ACTION_VERBS = {
    "open",
    "launch",
    "start",
    "run",
    "execute",
    "close",
    "quit",
    "exit",
    "kill",
    "minimise",
    "minimize",
    "maximise",
    "maximize",
    "switch",
    "play",
    "pause",
    "stop",
    "type",
    "write",
    "save",
    "delete",
    "remove",
    "create",
    "make",
    "copy",
    "paste",
    "cut",
    "click",
    "scroll",
    "search",
    "google",
    "download",
    "install",
    "send",
    "email",
    "screenshot",
    "mute",
    "unmute",
    "increase",
    "decrease",
    "set",
    "lock",
    "shutdown",
    "restart",
    "reboot",
    "sleep",
    "hibernate",
}

# Verbs aimed at JARVIS itself.
SYSTEM_VERBS = {
    "restart",
    "reboot",
    "shutdown",
    "reload",
    "reset",
    "sleep",
    "wake",
    "stop listening",
    "start listening",
}

# Openings that are always a request for information.
INFORMATION_PREFIX = re.compile(
    r"^\s*(?:"
    r"what|who|whom|whose|which|when|where|why|how|"
    r"tell\s+me|explain|describe|define|summari[sz]e|compare|list|"
    r"do\s+you\s+know|can\s+you\s+explain|can\s+you\s+tell|"
    r"i\s+want\s+to\s+know|i'?d\s+like\s+to\s+know|"
    r"let'?s\s+(?:discuss|talk)|give\s+me\s+(?:an?\s+)?(?:idea|overview|summary)"
    r")\b",
    re.IGNORECASE,
)

# "Can you open Notepad?" - polite wrapper around a real command.
POLITE_COMMAND = re.compile(
    r"^\s*(?:please\s+|can\s+you\s+|could\s+you\s+|would\s+you\s+|will\s+you\s+)+"
    r"(?P<verb>[a-z]+)\b",
    re.IGNORECASE,
)

# A bare imperative: the sentence starts with a verb.
IMPERATIVE = re.compile(r"^\s*(?:please\s+)?(?P<verb>[a-z]+)\b", re.IGNORECASE)

# Memory instructions are their own kind of request.
MEMORY_VERB = re.compile(
    r"^\s*(?:please\s+)?(?:remember|note|store|save\s+that|keep\s+in\s+mind|"
    r"don'?t\s+forget|forget|recall)\b",
    re.IGNORECASE,
)


def _first_clause(text: str) -> str:
    """The first sentence/clause - the one that carries the intent."""

    cleaned = (text or "").strip()

    if not cleaned:
        return ""

    parts = re.split(r"[.!?;\n]|,\s*(?:then|and\s+then)\b", cleaned, maxsplit=1)

    return parts[0].strip() or cleaned


def is_information_request(text: str) -> bool:
    """True when the user is asking *about* something."""

    clause = _first_clause(text)

    if not clause:
        return False

    polite = POLITE_COMMAND.match(clause)

    if polite and polite.group("verb").lower() in ACTION_VERBS:
        return False

    if INFORMATION_PREFIX.match(clause):
        return True

    if (text or "").strip().endswith("?"):
        return not POLITE_COMMAND.match(clause)

    # A plain declarative sentence is conversation, not a command:
    # "Python uses functions." / "JARVIS uses Python."  Only an action,
    # system or memory verb in command position changes that.
    if MEMORY_VERB.match(clause):
        return False

    lowered = clause.lower()

    if any(lowered.startswith(verb) for verb in SYSTEM_VERBS):
        return False

    imperative = IMPERATIVE.match(clause)

    if imperative and imperative.group("verb").lower() in ACTION_VERBS:
        return False

    if POLITE_COMMAND.match(clause):
        return False

    return True


def is_action_request(text: str) -> bool:
    """True when the user is telling JARVIS to *do* something."""

    clause = _first_clause(text)

    if not clause:
        return False

    if MEMORY_VERB.match(clause):
        return False

    polite = POLITE_COMMAND.match(clause)

    if polite:
        return polite.group("verb").lower() in ACTION_VERBS

    if is_information_request(text):
        return False

    imperative = IMPERATIVE.match(clause)

    if not imperative:
        return False

    return imperative.group("verb").lower() in ACTION_VERBS


def is_system_request(text: str) -> bool:
    """True for commands aimed at JARVIS itself ("Restart JARVIS.")."""

    clause = _first_clause(text).lower()

    if not clause or is_information_request(text):
        return False

    return any(clause.startswith(verb) for verb in SYSTEM_VERBS)


@dataclass
class RequestType:
    """What the current message is asking for."""

    kind: str = CONVERSATION
    action: bool = False
    information: bool = False


def classify(text: str) -> RequestType:
    """Classify one user message."""

    clause = _first_clause(text)

    if MEMORY_VERB.match(clause):
        return RequestType(kind=MEMORY, action=False, information=False)

    if is_system_request(text):
        return RequestType(kind=SYSTEM, action=True, information=False)

    if is_action_request(text):
        return RequestType(kind=ACTION, action=True, information=False)

    if (text or "").strip().endswith("?") or INFORMATION_PREFIX.match(clause):
        return RequestType(kind=QUESTION, action=False, information=True)

    return RequestType(kind=CONVERSATION, action=False, information=True)


__all__ = [
    "ACTION",
    "AUTOMATION",
    "CONVERSATION",
    "MEMORY",
    "QUESTION",
    "SYSTEM",
    "RequestType",
    "classify",
    "is_action_request",
    "is_information_request",
    "is_system_request",
]
