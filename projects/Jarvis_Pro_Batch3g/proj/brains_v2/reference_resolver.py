"""
Reference Resolver (brains_v2)

Backwards-compatible layer over the Conversation System resolver in
``conversation.reference_resolver``.

The original version understood only "it", "this", "that" and "there".
It now shares the full reference vocabulary of the Conversation System
(these, those, here, he, she, they, them, his, her, its) while keeping the
original public API - ``remember_entity``, ``remember_location`` and
``resolve`` - so existing callers and tests keep working.
"""

import re

from conversation.reference_resolver import (
    REFERENCE_WORDS as CONVERSATION_REFERENCES,
)


class ReferenceResolver:

    # Shared with the Conversation System resolver.
    REFERENCE_WORDS = set(CONVERSATION_REFERENCES)

    # References that point at a place rather than a thing.
    LOCATION_WORDS = {"there", "here"}

    def __init__(self):

        self.last_entity = None

        self.last_location = None

    def remember_entity(self, entity):

        value = str(entity).strip()

        if value:
            self.last_entity = value

    def remember_location(self, location):

        value = str(location).strip()

        if value:
            self.last_location = value

    def _references(self, command):
        """Reference words in the order they appear in the sentence."""

        words = re.findall(r"[a-z']+", str(command).lower())

        return [word for word in words if word in self.REFERENCE_WORDS]

    def resolve(self, command):
        """Resolve the first reference in ``command``.

        Returns ``{"resolved", "reference", "entity", "command"}`` where
        ``command`` is the sentence with the reference substituted.
        """

        text = str(command).strip()

        for reference in self._references(text):

            if reference in self.LOCATION_WORDS:
                target = self.last_location
            else:
                target = self.last_entity

            if target is None:

                return {

                    "resolved": False,

                    "reference": reference,

                    "entity": None,

                    "command": text

                }

            return {

                "resolved": True,

                "reference": reference,

                "entity": target,

                "command": re.sub(
                    rf"\b{re.escape(reference)}\b",
                    target,
                    text,
                    count=1,
                    flags=re.IGNORECASE
                )

            }

        return {

            "resolved": False,

            "reference": None,

            "entity": None,

            "command": text

        }


reference_resolver = ReferenceResolver()
