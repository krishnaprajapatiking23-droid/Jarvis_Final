"""
==========================================
JARVIS PRO
Output sanitizer - the single FINAL_USER_RESPONSE gate
==========================================

Why this module exists
----------------------
``qwen3`` is a reasoning model.  Depending on the client version and the
``think`` flag it can return its reasoning in three different shapes:

1. a separate ``message.thinking`` field (clean case),
2. an inline ``<think> ... </think>`` block inside ``message.content``,
3. *untagged* reasoning in front of the answer - "Okay, the user is
   asking ... Key points to cover: ... Final structure: ... <answer>".

Shape 3 is what leaked to the user.  Stripping ``<think>`` tags in the
provider was not enough, and every layer that touched a reply (provider,
variation layer, dialogue manager, controllers, TTS) had its own idea of
what "clean" meant.

This module is the one place that converts *anything* the model or the
pipeline produced into the text the user is allowed to see:

    MODEL RESPONSE
        -> extract final answer      (drop reasoning shapes 1-3)
        -> remove internal content   (prompt sections, debug, raw JSON)
        -> sanitize                  (whitespace, stray markers)
        -> USER-VISIBLE RESPONSE

It never tries to *show* hidden reasoning: reasoning is discarded, and
when nothing else is left the caller is told through ``LLMResult`` so it
can answer honestly instead of leaking the scratchpad.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

log = logging.getLogger("jarvis.conversation.sanitizer")

# ----------------------------------------------------------------------
# 1. Tagged reasoning (any of the common tag names, closed or not)
# ----------------------------------------------------------------------
THINK_TAGS = (
    "think",
    "thinking",
    "thought",
    "thoughts",
    "reason",
    "reasoning",
    "scratchpad",
    "analysis",
    "reflection",
    "plan",
)

CLOSED_BLOCK = re.compile(
    r"<\s*(%s)\s*>.*?<\s*/\s*\1\s*>" % "|".join(THINK_TAGS),
    re.IGNORECASE | re.DOTALL,
)

# A stray closing tag means everything before it was reasoning.
STRAY_CLOSE = re.compile(
    r"^.*?<\s*/\s*(?:%s)\s*>" % "|".join(THINK_TAGS),
    re.IGNORECASE | re.DOTALL,
)

# An opening reasoning tag that never closes.
OPEN_TAG = re.compile(
    r"<\s*(?:%s)\s*>" % "|".join(THINK_TAGS),
    re.IGNORECASE,
)

# ----------------------------------------------------------------------
# 2. Untagged reasoning markers
# ----------------------------------------------------------------------
# Lines that are planning scaffolding rather than an answer.
SCAFFOLD_LINE = re.compile(
    r"^\s*(?:[-*#>]+\s*)?(?:\*\*)?\s*(?:"
    r"key\s+points?(?:\s+to\s+cover)?|"
    r"points?\s+to\s+cover|"
    r"brainstorm(?:ing)?|"
    r"final\s+structure|"
    r"structure\s+of\s+the\s+(?:answer|response)|"
    r"draft(?:\s+\d+)?|"
    r"outline|"
    r"analysis|"
    r"reasoning|"
    r"chain\s+of\s+thought|"
    r"internal\s+notes?|"
    r"my\s+plan|"
    r"response\s+plan|"
    r"plan|"
    r"tone|"
    r"style\s+directive|"
    r"instructions?"
    r")\s*(?:\*\*)?\s*[:\-]",
    re.IGNORECASE,
)

# Prompt/debug sections that must never be echoed.
SECTION_LINE = re.compile(
    r"^\s*(?:\[(?:system|context|memory|router|llm|response|entities|topic|"
    r"session|state|summary|current\s+message|recent|long[-\s]?term|"
    r"environment|debug|trace)[^\]]*\]|"
    r"(?:system|developer|user)\s*:)",
    re.IGNORECASE,
)

# "Assistant: <answer>" - the label is internal, the answer is not.
ROLE_PREFIX = re.compile(r"^\s*(?:assistant|jarvis|ai)\s*:\s*", re.IGNORECASE)

# Bullets that belong to a scaffolding heading above them.
BULLET_LINE = re.compile(r"^\s*(?:[-*\u2022]|\d+[.)])\s+")

# First-person planning openers typical of leaked reasoning.
REASONING_OPENER = re.compile(
    r"^\s*(?:okay|ok|alright|right|hmm|so)\b[^.\n]{0,40}\b"
    r"(?:the\s+user|they)\b",
    re.IGNORECASE,
)

REASONING_PHRASES = (
    "let me think",
    "i need to figure out",
    "i should respond",
    "i should answer",
    "the user is asking",
    "the user wants",
    "first, i need to",
    "let me draft",
    "wait, the user",
    "as an ai language model i must",
)

# ----------------------------------------------------------------------
# 2b. Prompt echo
# ----------------------------------------------------------------------
# A reasoning model given a sectioned prompt sometimes *continues the
# prompt* instead of answering it: "We are in the middle of conversation
# about Python (the topic). The user has just asked ...", "RESPONSE
# DIRECTIVES ...", "But note: the system says ...".  That is our own
# scaffolding narrated back, so it is internal content, not an answer.
PROMPT_ECHO = (
    "we are in the middle of conversation",
    "we are in a situation where",
    "the user has just asked",
    "the user's last input",
    "the current message from user",
    "current message for which",
    "response directives",
    "from previous context:",
    "from context above",
    "from recent turns",
    "relevant earlier messages",
    "[current message",
    "the system says",
    "the system states",
    "the system instruction",
    "the problem says",
    "the problem states",
    "according to the latest instructions",
    "you have already answered this question before",
    "previous answer that i gave",
    "your earlier answer was",
    "but note:",
    "wait, the user",
    "wait a minute",
    "wait i'm confused",
    "i'm confused",
    "let me re-read",
    "let me reconstruct",
    "let me unpack",
    "let me clarify from",
    "let's unpack",
    "we must rewrite",
    "we must not repeat",
    "must add one useful detail",
    "must add at least one new useful detail",
    "for the purpose of this task",
    "for this specific reply",
    "for this specific response",
    "verifying constraints",
    "testing phrasing",
    "aha moment",
    "checks previous interaction",
    "user wants me to roleplay",
    "okay let's unpack",
)

# Where the real answer starts when the model announced it.
FINAL_MARKER = re.compile(
    r"^\s*(?:\*\*)?\s*(?:final\s+(?:answer|response|reply)|answer|response)"
    r"\s*(?:\*\*)?\s*[:\-]\s*",
    re.IGNORECASE | re.MULTILINE,
)


def _looks_like_reasoning(line: str) -> bool:
    """True when a single line is planning scaffolding, not an answer."""

    stripped = (line or "").strip()

    if not stripped:
        return False

    if SCAFFOLD_LINE.match(stripped) or SECTION_LINE.match(stripped):
        return True

    if REASONING_OPENER.match(stripped):
        return True

    lowered = stripped.lower()

    if any(phrase in lowered for phrase in PROMPT_ECHO):
        return True

    return any(phrase in lowered for phrase in REASONING_PHRASES)


def _strip_open_block(text: str) -> str:
    """Handle a reasoning tag that never closes.

    Everything on and after the tag is treated as reasoning *until* a
    line that reads like an answer, so a model that forgot the closing
    tag still gets its final sentence delivered.
    """

    match = OPEN_TAG.search(text)

    if not match:
        return text

    head = text[: match.start()]
    tail = text[match.end():]

    kept = []
    dropping = True

    for index, line in enumerate(tail.splitlines()):
        if dropping:
            if not line.strip():
                continue

            # The text on the tag's own line is always reasoning.
            if index == 0 or _looks_like_reasoning(line):
                continue

            dropping = False

        kept.append(line)

    recovered = "\n".join(kept).strip()

    if not recovered:
        return head

    return (head.strip() + "\n" + recovered).strip()


def _strip_tagged(text: str) -> str:
    """Remove every tagged reasoning block."""

    cleaned = CLOSED_BLOCK.sub(" ", text)

    if re.search(r"<\s*/\s*(?:%s)\s*>" % "|".join(THINK_TAGS), cleaned, re.I):
        cleaned = STRAY_CLOSE.sub(" ", cleaned)

    return _strip_open_block(cleaned)


def _after_final_marker(text: str) -> str:
    """Text after the last "Final answer:" style marker, if any."""

    matches = list(FINAL_MARKER.finditer(text))

    if not matches:
        return text

    tail = text[matches[-1].end():].strip()

    return tail or text


def _drop_reasoning_lines(text: str) -> str:
    """Drop scaffolding lines, keeping the answer they were wrapped around."""

    kept = []
    dropping_bullets = False

    for line in text.splitlines():
        role = ROLE_PREFIX.match(line)

        if role:
            # Keep the answer, drop the speaker label.
            line = line[role.end():]

            if not line.strip():
                continue

        if _looks_like_reasoning(line):
            dropping_bullets = True
            continue

        if dropping_bullets:
            if not line.strip():
                dropping_bullets = False
                continue

            if BULLET_LINE.match(line):
                # A list under a scaffolding heading is scaffolding.
                continue

            dropping_bullets = False

        kept.append(line)

    if not any(line.strip() for line in kept):
        # Everything looked internal - keep the original so the caller can
        # see (through ``leaked``) that there is no deliverable answer.
        return text

    return "\n".join(kept)


def _unwrap_json(text: str) -> str:
    """Recover the answer when a raw model payload was stringified."""

    stripped = text.strip()

    if not stripped.startswith(("{", "[")):
        return text

    try:
        payload = json.loads(stripped)
    except Exception:
        return text

    if isinstance(payload, list) and payload:
        payload = payload[0]

    if not isinstance(payload, dict):
        return text

    message = payload.get("message")

    if isinstance(message, dict):
        content = message.get("content")

        if isinstance(content, str) and content.strip():
            return content

    for key in ("response", "content", "text", "final_text"):
        value = payload.get(key)

        if isinstance(value, str) and value.strip():
            return value

    return text


def _tidy(text: str) -> str:
    """Collapse blank runs and trim stray markers."""

    cleaned = re.sub(r"\n{3,}", "\n\n", text)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)

    return cleaned.strip().strip("`").strip()


def looks_internal(text: str) -> bool:
    """True when ``text`` still shows signs of internal content."""

    if not text:
        return False

    lowered = text.lower()

    if "<think" in lowered or "</think" in lowered:
        return True

    if any(phrase in lowered for phrase in REASONING_PHRASES):
        return True

    if any(phrase in lowered for phrase in PROMPT_ECHO):
        return True

    return any(_looks_like_reasoning(line) for line in text.splitlines())


def sanitize(text: Any) -> str:
    """Return only the user-visible part of ``text``."""

    if text is None:
        return ""

    if not isinstance(text, str):
        text = str(text)

    if not text.strip():
        return ""

    cleaned = _unwrap_json(text)
    cleaned = _strip_tagged(cleaned)
    cleaned = _after_final_marker(cleaned)
    cleaned = _drop_reasoning_lines(cleaned)

    return _tidy(cleaned)


@dataclass
class LLMResult:
    """Standardised model result - the only shape the app passes around."""

    final_text: str = ""
    success: bool = True
    model: str = ""
    reason: str = ""
    leaked: bool = False
    raw_length: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __bool__(self) -> bool:  # pragma: no cover - convenience
        return bool(self.final_text)

    def __str__(self) -> str:  # pragma: no cover - convenience
        return self.final_text


def final_user_response(
    raw: Any,
    model: str = "",
    reason: str = "",
    metadata: Optional[Dict[str, Any]] = None,
) -> LLMResult:
    """Convert any model/pipeline output into a clean ``LLMResult``.

    ``leaked`` records that internal content had to be removed, so the
    developer log shows it even though the user never sees it.
    """

    original = "" if raw is None else str(raw)
    cleaned = sanitize(original)

    leaked = bool(original.strip()) and (
        len(cleaned) < len(original.strip()) or looks_internal(original)
    )

    if cleaned and looks_internal(cleaned):
        # The text survived cleaning but still reads as internal: refuse
        # it rather than shipping a scratchpad to the user.
        log.warning("internal content could not be separated from the answer")

        return LLMResult(
            final_text="",
            success=False,
            model=model,
            reason=reason or "internal_only",
            leaked=True,
            raw_length=len(original),
            metadata=dict(metadata or {}),
        )

    if not cleaned:
        return LLMResult(
            final_text="",
            success=False,
            model=model,
            reason=reason or ("internal_only" if leaked else "empty"),
            leaked=leaked,
            raw_length=len(original),
            metadata=dict(metadata or {}),
        )

    if leaked:
        log.info("sanitized %s chars of internal content", len(original) - len(cleaned))

    return LLMResult(
        final_text=cleaned,
        success=True,
        model=model,
        reason=reason,
        leaked=leaked,
        raw_length=len(original),
        metadata=dict(metadata or {}),
    )


__all__ = [
    "LLMResult",
    "PROMPT_ECHO",
    "final_user_response",
    "looks_internal",
    "sanitize",
]
