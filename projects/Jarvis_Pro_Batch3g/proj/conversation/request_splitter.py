"""
==========================================
JARVIS PRO
Request Splitter
==========================================

One user message can carry several jobs:

    "Remember that my project is called JARVIS. What is my project called?"
        memory  -> project = JARVIS
        question-> What is my project called?

Before this module the whole sentence - question included - was handed to
the memory system, which is why JARVIS answered:

    "Okay Krishna, I will remember that your project is called JARVIS.
     What is my project called?."

``split()`` separates a message into

* ``memory``     - explicit "remember / note / don't forget" instructions
* ``statements`` - plain declarative sentences (conversation context)
* ``questions``  - anything the user actually asked

and ``parse_fact()`` turns "my project is called JARVIS" into
``("project", "JARVIS")``.

Only *explicit* instructions count as memory commands.  "My favorite
language is Python. What did I just tell you?" is conversation with a
history question, exactly as the bug report requires.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Tuple

# "remember that X", "note this: X", "don't forget X", "keep in mind X"
MEMORY_INSTRUCTION = re.compile(
    r"^(?:please\s+)?(?:jarvis[,\s]+)?"
    r"(?:remember|memorise|memorize|note|store|save|keep\s+in\s+mind|"
    r"don'?t\s+forget)"
    r"(?:\s+(?:that|this|the\s+following))?"
    r"\s*[:,-]?\s*(?P<fact>.+)$",
    re.IGNORECASE,
)

# Labels users put in front of the real fact: "important fact: my project..."
FACT_LABEL = re.compile(
    r"^(?:very\s+)?(?:important|key|useful)?\s*"
    r"(?:fact|detail|point|thing|note)\s*[:\-]\s*(?P<fact>.+)$",
    re.IGNORECASE,
)

# "my project is called JARVIS" / "my favourite language is Python"
FACT_PATTERN = re.compile(
    r"^(?:my|our)\s+(?P<key>[a-z0-9 _'-]{2,40}?)\s+"
    r"(?:is|are)\s+(?:called|named|going\s+to\s+be)?\s*(?P<value>.+)$",
    re.IGNORECASE,
)

GENERIC_FACT = re.compile(
    r"^(?P<key>[a-z0-9 _'-]{2,40}?)\s+(?:is|are)\s+"
    r"(?:called|named)?\s*(?P<value>.+)$",
    re.IGNORECASE,
)

QUESTION_STARTERS = (
    "what", "who", "when", "where", "why", "how", "which", "whose",
    "is", "are", "was", "were", "do", "does", "did", "can", "could",
    "will", "would", "should", "am", "have", "has",
)

# Sentence boundaries, keeping the punctuation with the sentence.
_SENTENCE = re.compile(r"[^.!?;]+[.!?;]?")

ELLIPSIS = re.compile(r"(\.{2,}|\u2026)\s*$")


def sentences(text: str) -> List[str]:
    """Split ``text`` into trimmed sentences (ellipses kept intact)."""

    raw = (text or "").strip()

    if not raw:
        return []

    # Protect "..." so it is not read as three sentence ends.
    guarded = raw.replace("...", "\u2026")

    found = [part.strip() for part in _SENTENCE.findall(guarded)]

    return [part.replace("\u2026", "...") for part in found if part]


def is_question(sentence: str) -> bool:
    """True when ``sentence`` asks something."""

    text = (sentence or "").strip().lower()

    if not text:
        return False

    if text.endswith("?"):
        return True

    words = text.strip(".!;").split()

    if not words:
        return False

    if words[0] in QUESTION_STARTERS:
        return True

    # "tell me what my project is called"
    return text.startswith(("tell me what", "tell me who", "tell me when"))


def parse_fact(fact: str) -> Tuple[str, str]:
    """Turn a fact sentence into ``(key, value)``; ``("", "")`` when unclear."""

    text = (fact or "").strip().rstrip(".!;")

    if not text:
        return "", ""

    labelled = FACT_LABEL.match(text)

    if labelled:
        text = labelled.group("fact").strip()

    for pattern in (FACT_PATTERN, GENERIC_FACT):
        match = pattern.match(text)

        if not match:
            continue

        key = " ".join(match.group("key").split()).lower()
        value = match.group("value").strip().rstrip(".!;")

        key = re.sub(r"^(?:my|our|the)\s+", "", key).strip()

        if key and value:
            return key, value

    return "", ""


@dataclass
class SplitRequest:
    """The jobs contained in one user message."""

    text: str = ""
    memory: List[str] = field(default_factory=list)
    statements: List[str] = field(default_factory=list)
    questions: List[str] = field(default_factory=list)
    incomplete: bool = False

    @property
    def has_memory(self) -> bool:
        return bool(self.memory)

    @property
    def has_question(self) -> bool:
        return bool(self.questions)

    @property
    def question(self) -> str:
        return self.questions[0] if self.questions else ""

    def facts(self) -> List[Tuple[str, str]]:
        """``(key, value)`` for every memory instruction that parses."""

        pairs = []

        for item in self.memory:
            key, value = parse_fact(item)

            if key and value:
                pairs.append((key, value))

        return pairs


def split(text: str) -> SplitRequest:
    """Separate memory instructions, statements and questions."""

    result = SplitRequest(text=(text or "").strip())

    for sentence in sentences(text):

        if ELLIPSIS.search(sentence):
            result.incomplete = True
            result.statements.append(sentence)
            continue

        if is_question(sentence):
            result.questions.append(sentence.strip())
            continue

        instruction = MEMORY_INSTRUCTION.match(sentence)

        if instruction:
            fact = instruction.group("fact").strip().rstrip(".!;")

            if fact:
                result.memory.append(fact)

            continue

        result.statements.append(sentence.strip())

    return result


__all__ = [
    "SplitRequest",
    "split",
    "sentences",
    "is_question",
    "parse_fact",
]
