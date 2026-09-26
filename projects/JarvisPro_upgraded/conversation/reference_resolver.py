"""
==========================================
JARVIS PRO
Reference Resolver  (features 3.9, 3.10)
==========================================

Resolves pronouns and demonstratives against the conversation state:

    "Open Notepad."  ->  "Close it."       ->  it = Notepad
    "Who is Elon Musk?" -> "How old is he?" -> he = Elon Musk

ROOT CAUSE REPAIRED HERE
------------------------
The previous version substituted *every* occurrence of a reference word
using ``state.current_topic`` as a fallback, ignoring grammar and the type
of the referent.  That produced the reported bugs:

    "Open it."                                  -> "open python."
    "I've explained this three times ..."       -> "i've explained file ..."
    "I want to create a system that can..."     -> "... a system python can"

Three rules now prevent that:

1. ``_used_as_reference()`` - a word only counts as a reference when it is
   used pronominally.  Determiners ("this project", "that file"), relative
   clauses ("a system that can ...") and idioms are ignored.
2. For an action request ("open it", "send that") only *actionable*
   entities qualify - a conversation topic is not something you can open.
   Nothing suitable in state means the word stays unresolved so the
   ambiguity detector can ask "What would you like me to open?".
3. Substitution is skipped when the entity name is already in the text, so
   a resolved sentence is never mangled.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List

from conversation.conversation_state import ConversationState
from conversation.entity_tracker import APP, OBJECT, PERSON, PLACE

log = logging.getLogger("jarvis.conversation.references")

# reference word -> preferred entity types, in order
REFERENCE_WORDS: Dict[str, tuple] = {
    "it": (APP, OBJECT, "topic", "project", "company"),
    "its": (APP, OBJECT, "topic", "project", "company"),
    "this": (APP, OBJECT, "topic", "project"),
    "that": (APP, OBJECT, "topic", "project"),
    "these": (APP, OBJECT, "topic"),
    "those": (APP, OBJECT, "topic"),
    "them": (APP, OBJECT, PERSON),
    "they": (PERSON, APP, OBJECT),
    "he": (PERSON,),
    "him": (PERSON,),
    "his": (PERSON,),
    "she": (PERSON,),
    "her": (PERSON,),
    "hers": (PERSON,),
    "there": (PLACE,),
    "here": (PLACE,),
}

# "is it difficult" style follow-ups: the reference points at the topic.
TOPIC_PREFERRING = {"it", "this", "that", "its"}

# Types you can actually act on.  A discussion topic is not one of them.
ACTIONABLE_TYPES = {
    APP,
    OBJECT,
    "file",
    "project",
    "application",
    "program",
    "software",
    "document",
}

# Different parts of the project name the same thing differently, so a
# referent typed "application" must still answer to APP.
TYPE_ALIASES = {
    APP: ("application", "app", "program", "software"),
    OBJECT: ("object", "file", "document", "item"),
}

# Verbs that make the sentence an action request.
ACTION_VERBS = (
    "open", "close", "start", "stop", "launch", "run", "play", "pause",
    "send", "share", "mail", "email", "forward", "upload", "download",
    "delete", "remove", "rename", "move", "copy", "install", "print",
    "save", "kill", "minimize", "maximize", "focus",
)

# Words that follow a *determiner* use: "this project", "that file".
DETERMINER_FOLLOWERS = re.compile(
    r"^(?:[a-z]+ly\s+)?[a-z][a-z'-]*\b", re.IGNORECASE
)

# Verb-ish words that mark "that" as a relative pronoun: "a system that can".
CLAUSE_VERBS = {
    "is", "are", "was", "were", "can", "could", "will", "would", "should",
    "has", "have", "had", "does", "do", "did", "may", "might", "must",
}

RELATIVE_FOLLOWERS = CLAUSE_VERBS | {
    "i", "you", "we", "they", "he", "she", "it",
}

# Numbers/nouns that make "this/that" a quantifier: "this three times".
COUNT_WORDS = {
    "one", "two", "three", "four", "five", "six", "seven", "eight",
    "nine", "ten", "many", "much", "few", "several", "time", "times",
    "way", "morning", "evening", "afternoon", "week", "month", "year",
}

# Phrases that contain a reference word but are not references.
IDIOMS = (
    "that's all",
    "thats all",
    "that is all",
    "that's it",
    "thats it",
    "that's enough",
    "thats enough",
    "it worked",
    "it works",
    "it is not working",
    "it isn't working",
    "it's not working",
    "its not working",
    "there you go",
    "that's right",
    "thats right",
    "that's true",
)

# BUG FIX: "what time is it" was resolved against the most recent entity,
# producing "what time is calculator" -- which then matched the decision
# engine's "calculator" keyword and tried to LAUNCH AN APP. In these fixed
# expressions "it" is a dummy subject with no referent, so leave it alone.
DUMMY_IT = re.compile(
    r"\b(?:what|which|how)\s+(?:time|day|date|month|year|hour)\b"
    r"|\bwhat(?:'s| is|s)\s+(?:the\s+)?(?:time|date|day|weather)\b"
    r"|\bhow\s+(?:late|early|cold|hot|warm|windy)\s+is\s+it\b"
    r"|\bis\s+it\s+(?:raining|snowing|sunny|cold|hot|late|early|morning|"
    r"afternoon|evening|night|monday|tuesday|wednesday|thursday|friday|"
    r"saturday|sunday)\b"
    r"|\bit\s+(?:is|was|will\s+be)\s+(?:raining|snowing|sunny|cold|hot|late)\b",
    re.IGNORECASE,
)


def _is_action(text: str) -> str:
    """The action verb in ``text``, or "" when it is not an action request."""

    lowered = (text or "").lower()

    for verb in ACTION_VERBS:
        if re.search(rf"\b{verb}\b", lowered):
            return verb

    return ""


class ReferenceResolver:
    """Replaces reference words with the entity they point to."""

    # ------------------------------------------------------------------
    def _used_as_reference(self, word: str, lowered: str, start: int, end: int) -> bool:
        """True when ``word`` at this position is really a pronoun."""

        before = lowered[:start].strip().split()
        after = lowered[end:].strip()
        next_word = after.split()[0].strip(".,!?;:") if after else ""

        if word in {"this", "that", "these", "those"}:

            # "a system that can ...", "the file that I sent"
            if next_word in RELATIVE_FOLLOWERS:
                return False

            # "this three times", "that morning"
            if next_word in COUNT_WORDS or next_word.isdigit():
                return False

            # "this project", "that file" -> determiner + noun
            if next_word and next_word not in CLAUSE_VERBS:
                if not next_word.endswith(("?", "!")):
                    return False

        if word in {"it", "its"}:

            # "it should", "it is" are pronominal - keep them.
            # "its memory system" is possessive but still a reference.
            if before and before[-1] in {"of", "about"} and not next_word:
                return True

        if word in {"here", "there"}:

            # "there is", "there are" - existential, not a place.
            if next_word in {"is", "are", "was", "were", "will", "you"}:
                return False

        return True

    # ------------------------------------------------------------------
    def find_references(self, text: str) -> List[str]:
        """Reference words genuinely used as references, in order."""

        if not text:
            return []

        lowered = text.lower()

        if any(idiom in lowered for idiom in IDIOMS):
            return []

        # Dummy "it" ("what time is it") has no referent to substitute.
        if DUMMY_IT.search(lowered):
            return []

        found: List[str] = []

        for match in re.finditer(r"\b([a-z']+)\b", lowered):
            word = match.group(1)

            if word not in REFERENCE_WORDS or word in found:
                continue

            if not self._used_as_reference(word, lowered, match.start(1), match.end(1)):
                continue

            found.append(word)

        return found

    # ------------------------------------------------------------------
    def candidates(
        self,
        word: str,
        state: ConversationState,
        actionable_only: bool = False,
    ) -> List[Dict[str, Any]]:
        """Entities that could satisfy ``word``, best first."""

        preferred = REFERENCE_WORDS.get(word, ())
        ranked: List[Dict[str, Any]] = []

        # Anything active counts, even if it never reached the recent
        # window (a caller may set active entities directly).
        pool = list(state.recent_entities)
        for entity in state.active_entities:
            if entity not in pool:
                pool.append(entity)

        for type in preferred:
            if actionable_only and type not in ACTIONABLE_TYPES:
                continue

            names = {type, *TYPE_ALIASES.get(type, ())}

            for entity in pool:
                if entity.get("type") in names and entity not in ranked:
                    ranked.append(entity)

        # "is it hard?" after "tell me about Python" -> the topic itself.
        # Never for an action request: you cannot "open" a topic.
        if not actionable_only and word in TOPIC_PREFERRING and state.current_topic:
            topic_entity = {
                "name": state.current_topic,
                "type": "topic",
                "text": state.current_topic.lower(),
                "source": "topic",
            }

            if not any(
                str(entity.get("name", "")).lower() == state.current_topic.lower()
                for entity in ranked
            ):
                ranked.append(topic_entity)

        return ranked

    # ------------------------------------------------------------------
    def resolve(self, text: str, state: ConversationState) -> Dict[str, Any]:
        """Resolve every reference word in ``text``.

        Returns::

            {
                "original": str,
                "resolved": str,          # text with references substituted
                "changed": bool,
                "references": ["it"],
                "mapping": {"it": "Chrome"},
                "entities": [entity, ...],
                "unresolved": ["it"],
                "candidates": {"it": [entity, ...]},
                "action": "open",         # "" when not an action request
            }
        """

        result: Dict[str, Any] = {
            "original": text,
            "resolved": text,
            "changed": False,
            "references": [],
            "mapping": {},
            "entities": [],
            "unresolved": [],
            "candidates": {},
            "action": "",
        }

        if not text or not text.strip():
            return result

        try:
            words = self.find_references(text)
        except Exception as error:  # pragma: no cover - defensive
            log.warning("reference scan failed: %s", error)
            return result

        action = _is_action(text)
        result["action"] = action

        if not words:
            return result

        result["references"] = words
        resolved_text = text

        for word in words:
            options = self.candidates(word, state, actionable_only=bool(action))
            result["candidates"][word] = options

            if not options:
                result["unresolved"].append(word)
                log.debug("no referent for %r in %r", word, text)
                continue

            entity = options[0]
            name = str(entity.get("name", "")).strip()

            if not name:
                result["unresolved"].append(word)
                continue

            result["mapping"][word] = name
            result["entities"].append(entity)

            # Already explicit - don't rewrite the sentence.
            if re.search(rf"\b{re.escape(name)}\b", resolved_text, re.IGNORECASE):
                continue

            resolved_text = re.sub(
                rf"\b{re.escape(word)}\b",
                name,
                resolved_text,
                count=1,
                flags=re.IGNORECASE,
            )

        result["resolved"] = resolved_text
        result["changed"] = resolved_text != text

        return result


reference_resolver = ReferenceResolver()

__all__ = [
    "ReferenceResolver",
    "reference_resolver",
    "REFERENCE_WORDS",
    "ACTIONABLE_TYPES",
]
