"""
==========================================
JARVIS PRO
Key/value memory engine
==========================================

``process_memory()`` used to do three wrong things:

* it treated everything after the word "remember" as the fact, so the
  question in "Remember that my project is called JARVIS. What is my
  project called?" was stored as part of the value;
* it hard-coded the owner name in the reply;
* it never answered the question that came with the instruction.

It now uses ``conversation.request_splitter`` to separate the memory
instruction, the fact and the question, and supports the six memory
operations the conversation system needs:

    STORE          "Remember that my project is called JARVIS."
    RECALL         "What is my project called?"
    STORE + RECALL "Remember ... . What did I ask you to remember?"
    UPDATE         "My project is called JARVIS 2."
    CORRECT        "Actually, correction: it uses Python."
    DELETE         "Forget my favourite colour."

A correction always overwrites the value it corrects, so the active fact
is "Python", never "Java + Python".
"""

import logging
import re

from memory.database import connect
from conversation.request_splitter import parse_fact, split

log = logging.getLogger("jarvis.memory.engine")

# Question wordings mapped to the stored key.
ALIASES = {
    "favorite programming language": "language",
    "favourite programming language": "language",
    "programming language": "language",
    "favorite language": "language",
    "favourite language": "language",
}

# "What is my project called?"
QUESTION_KEY = re.compile(
    r"\b(?:what|which)\s+(?:is|are|was|were)\s+(?:my|our|the)\s+"
    r"(?P<key>[a-z0-9 _'-]{2,40}?)\s*(?:called|named)?\s*\??$",
    re.IGNORECASE,
)

# "What language does my project use now?"
QUESTION_USES = re.compile(
    r"\b(?:what|which)\s+(?P<thing>language|framework|database|tool|editor)\s+"
    r"(?:does|do|is)\s+(?:my|our|the)?\s*(?P<subject>[a-z0-9 _'-]{2,40}?)\s*"
    r"(?:use|using|used|written\s+in|built\s+with|run\s+on)?\s*(?:now|currently)?\s*\??$",
    re.IGNORECASE,
)

# "What did I ask you to remember?"
QUESTION_LAST = re.compile(
    r"\bwhat\s+(?:did|have)\s+i\s+(?:ask(?:ed)?|tell|told)\s+you\s+"
    r"(?:to\s+remember|to\s+note|about)?",
    re.IGNORECASE,
)

# "My project uses Python." / "JARVIS is written in Python."
USES_FACT = re.compile(
    r"^(?:my|our)?\s*(?P<subject>[a-z0-9 _'-]{2,40}?)\s+"
    r"(?:uses|use|is\s+written\s+in|is\s+built\s+with|runs\s+on)\s+"
    r"(?P<value>[^,]{1,60})$",
    re.IGNORECASE,
)

# "My project is called JARVIS." - a fact stated without "remember".
STRICT_FACT = re.compile(
    r"^(?:my|our)\s+(?P<key>[a-z0-9 _'-]{2,40}?)\s+is\s+"
    r"(?:called\s+|named\s+)?(?P<value>[^,]{1,60})$",
    re.IGNORECASE,
)

# "Actually, ..." / "Correction: ..." / "Sorry, I meant ..."
CORRECTION = re.compile(
    r"^\s*(?:actually|correction|sorry|no|oops|i\s+mean|i\s+meant|"
    r"scratch\s+that|let\s+me\s+correct\s+that)\b[,:\-\s]*(?P<rest>.*)$",
    re.IGNORECASE,
)

# "change my favourite colour to green" - the key is named.
CHANGE_KEY_TO = re.compile(
    r"^(?:change|update|set|make)\s+(?:my|our|the)\s+"
    r"(?P<key>[a-z0-9 _'-]{2,40}?)\s+(?:to|into|=)\s+(?P<value>[^,]{1,60})$",
    re.IGNORECASE,
)

# "change it to Python" / "make it Python"
CHANGE_TO = re.compile(
    r"^(?:change|update|set|make)\s+(?:it|that|this|the\s+\w+)?\s*"
    r"(?:to|into|=)?\s*(?P<value>[^,]{1,60})$",
    re.IGNORECASE,
)

# "Forget my favourite colour."
FORGET = re.compile(
    r"^\s*(?:please\s+)?forget\s+(?:about\s+)?(?:my|our|the)?\s*"
    r"(?P<key>[a-z0-9 _'-]{2,40})\s*$",
    re.IGNORECASE,
)

# "... Java now" / "... Python instead" - the value is the first word(s).
TRAILING_TIME = re.compile(
    r"\s+(?:now|currently|instead|today|from\s+now\s+on|going\s+forward)$",
    re.IGNORECASE,
)

# Subjects that are references, not entities.
PRONOUNS = {"it", "that", "this", "they", "them", "he", "she", "there"}

# The fact touched most recently - a correction with no explicit subject
# ("Actually, change it to Python") applies to this key.
_LAST = {"key": "", "value": ""}


def remember(key, value):
    conn = connect()
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT OR REPLACE INTO memories(key, value)
        VALUES(?, ?)
        """,
        (key.lower(), value)
    )

    conn.commit()
    conn.close()


def recall(key):
    conn = connect()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT value FROM memories
        WHERE key=?
        """,
        (key.lower(),)
    )

    row = cursor.fetchone()

    conn.close()

    if row:
        return row[0]

    return None


def forget(key):
    """Delete one stored fact.  Returns True when something was removed."""

    conn = connect()
    cursor = conn.cursor()

    cursor.execute("DELETE FROM memories WHERE key=?", (key.lower(),))
    removed = cursor.rowcount > 0

    conn.commit()
    conn.close()

    return removed


def last_fact():
    """The most recently stored/updated ``(key, value)``."""

    return _LAST["key"], _LAST["value"]


def _owner():
    """Owner name from settings - never hard-coded."""

    try:
        from conversation.identity import identity

        return identity.owner()

    except Exception:  # pragma: no cover - defensive
        return ""


def _normalise_key(key):
    key = " ".join((key or "").split()).lower()
    key = re.sub(r"^(?:my|our|the)\s+", "", key)

    return ALIASES.get(key, key)


def _store(key, value):
    """Write one fact and remember that it is the active one."""

    key = _normalise_key(key)
    value = (value or "").strip().rstrip(".!")

    # "JARVIS uses Java now" means the value is "Java"; the trailing word
    # only says that this replaces the previous value.
    value = TRAILING_TIME.sub("", value).strip().rstrip(".!")

    if not key or not value:
        return "", ""

    remember(key, value)

    _LAST["key"] = key
    _LAST["value"] = value

    log.debug("stored %s=%s", key, value)

    return key, value


def _plain_fact(sentence):
    """Fact stated without the word "remember", or ``("", "")``."""

    text = (sentence or "").strip().rstrip(".!;")

    if not text:
        return "", ""

    strict = STRICT_FACT.match(text)

    if strict:
        return (
            _normalise_key(strict.group("key")),
            strict.group("value").strip(),
        )

    uses = USES_FACT.match(text)

    if uses:
        subject = _normalise_key(uses.group("subject"))

        # "it uses Python" carries no subject of its own - the caller
        # resolves the pronoun against the active fact instead.
        if not subject or subject in PRONOUNS:
            return "", ""

        return f"{subject} language", uses.group("value").strip()

    return "", ""


def _apply_correction(sentence, active_key):
    """Apply "Actually, ..." style corrections.  Returns the new fact."""

    text = (sentence or "").strip().rstrip(".!;")

    if not text:
        return "", ""

    match = CORRECTION.match(text)

    if not match:
        return "", ""

    rest = match.group("rest").strip()

    # "Actually, correction: it uses Python." - markers can chain.
    while True:
        nested = CORRECTION.match(rest)

        if not nested or nested.group("rest").strip() == rest:
            break

        rest = nested.group("rest").strip()

    if not rest:
        return "", ""

    # "Actually, my project uses Python." - full fact restated.
    key, value = _plain_fact(rest)

    if key and value:
        return _store(key, value)

    # "Actually, remember that my project uses Python."
    key, value = parse_fact(rest)

    if key and value:
        return _store(key, value)

    # "Actually, change my favourite colour to green." - key named.
    named = CHANGE_KEY_TO.match(rest)

    if named:
        return _store(named.group("key"), named.group("value"))

    # "Actually, change it to Python." - value only, subject implied.
    change = CHANGE_TO.match(rest)

    if change and active_key:
        return _store(active_key, change.group("value"))

    # "Actually, it uses Python."
    tail = re.match(
        r"^(?:it|that|this)\s+(?:uses|is\s+written\s+in|is\s+called|is)\s+"
        r"(?P<value>[^,]{1,60})$",
        rest,
        re.IGNORECASE,
    )

    if tail and active_key:
        return _store(active_key, tail.group("value"))

    return "", ""


def _fact_reply(key, value):
    """Phrase a stored fact naturally."""

    if key.endswith(" language"):
        subject = key[: -len(" language")]

        return f"Your {subject} uses {value}."

    return f"Your {key} is {value}."


def _answer(question):
    """Answer ``question`` from stored memory, or return ""."""

    text = (question or "").strip()

    if not text:
        return ""

    stripped = text.rstrip(".!")

    # "What did I ask you to remember?"
    if QUESTION_LAST.search(stripped):
        key, value = last_fact()

        if key and value:
            return "You asked me to remember this: " + _fact_reply(key, value)

        return ""

    # "What language does my project use now?"
    uses = QUESTION_USES.search(stripped)

    if uses:
        subject = _normalise_key(uses.group("subject"))
        thing = uses.group("thing").lower()

        if not subject or subject in PRONOUNS:
            # "What language does it use?" - "it" is the fact we just
            # stored or corrected in this same message.
            active, _ = last_fact()
            value = recall(active) if active else None
        else:
            value = recall(f"{subject} {thing}") or recall(subject)

        if value:
            return f"It uses {value}."

    # "What is my project called?"
    match = QUESTION_KEY.search(stripped)

    if match:
        key = _normalise_key(match.group("key"))
        value = recall(key)

        if value:
            return _fact_reply(key, value)

    return ""


def process_memory(user_input):
    """Handle memory writes, updates, corrections, deletions and recalls.

    Returns the reply text, or None when this is not a memory message so
    the conversation system keeps ownership of the turn.
    """

    text = (user_input or "").strip()

    if not text:
        return None

    request = split(text)

    stored = []
    active_key = ""

    # ==========================
    # DELETE
    # ==========================
    for sentence in list(request.memory) + list(request.statements):
        drop = FORGET.match((sentence or "").strip().rstrip(".!"))

        if drop:
            key = _normalise_key(drop.group("key"))

            if forget(key):
                return f"Done - I've forgotten your {key}."

            return f"I don't have anything stored for your {key}."

    # ==========================
    # STORE (explicit "remember ..." instruction)
    # ==========================
    for fact in request.memory:
        key, value = parse_fact(fact)

        if not key or not value:
            # "remember that my project uses Java" states the fact with a
            # verb rather than "is", so parse_fact cannot see it.
            key, value = _plain_fact(fact)

        if not key or not value:
            continue

        key, value = _store(key, value)

        if key:
            stored.append((key, value))
            active_key = key

    if not active_key:
        active_key, _ = last_fact()

    # ==========================
    # CORRECT / UPDATE / plain statements of fact
    # ==========================
    corrected = False

    for sentence in request.statements:
        key, value = _apply_correction(sentence, active_key)

        if key and value:
            stored.append((key, value))
            active_key = key
            corrected = True
            continue

        key, value = _plain_fact(sentence)

        if key and value:
            key, value = _store(key, value)

            if key:
                stored.append((key, value))
                active_key = key

    # ==========================
    # RECALL
    # ==========================
    if request.has_question:
        answer = _answer(request.question)

        if answer:
            if corrected:
                return f"Updated - {answer}"

            if stored and request.has_memory:
                return f"Noted. {answer}"

            return answer

        if stored:
            # The fact is saved; let the conversation system answer the
            # question with full context instead of ignoring it.
            log.debug("stored %s, passing the question on", stored[-1][0])

        return None

    # ==========================
    # Acknowledge an explicit instruction
    # ==========================
    if request.has_memory and stored:
        key, value = stored[-1]
        owner = _owner()
        lead = f"Got it{', ' + owner if owner else ''}"

        return f"{lead} - I'll remember that your {key} is {value}."

    if corrected and stored:
        key, value = stored[-1]

        return f"Updated - your {key} is {value} now."

    # ==========================
    # Not a memory message
    # ==========================
    return None
