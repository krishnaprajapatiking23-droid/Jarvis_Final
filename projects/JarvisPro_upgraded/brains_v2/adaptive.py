"""
==========================================
JARVIS PRO
Adaptive familiarity level
==========================================

Tracks how familiar JARVIS is with the owner so the tone can soften over
time.  Two problems were fixed here:

1. ``update()`` read ``relationship["talks"]`` directly, but the caller
   (``reply_controller``) passes ``personality.data()``, which only holds
   ``mode`` and ``mood``.  Every reply going through the reply controller
   raised ``KeyError: 'talks'``.  It now accepts any mapping and counts
   turns itself when no count is supplied.
2. ``prefix()`` used to be glued to the front of every answer.  Nothing
   calls it automatically any more - openings are decided per turn by the
   response planner.
"""

from conversation.identity import identity

FORMAL_UNTIL = 20
FRIENDLY_UNTIL = 100


class AdaptiveEngine:

    def __init__(self):

        self.level = "formal"
        self.talks = 0

    # ------------------------------------------------------------------
    def update(self, relationship=None):
        """Refresh the familiarity level.

        ``relationship`` may be any mapping.  If it carries a turn count
        (``talks`` / ``conversations`` / ``count`` / ``turns``) that value
        is used, otherwise the engine counts the turns it has seen.
        """

        talks = None

        if isinstance(relationship, dict):

            for key in ("talks", "conversations", "count", "turns"):

                value = relationship.get(key)

                if isinstance(value, (int, float)):

                    talks = int(value)
                    break

        elif isinstance(relationship, (int, float)):

            talks = int(relationship)

        if talks is None:

            self.talks += 1
            talks = self.talks

        else:

            self.talks = talks

        if talks < FORMAL_UNTIL:

            self.level = "formal"

        elif talks < FRIENDLY_UNTIL:

            self.level = "friendly"

        else:

            self.level = "best_friend"

        return self.level

    # ------------------------------------------------------------------
    def prefix(self):
        """Address phrase for the current familiarity level.

        Kept for compatibility with older callers; nothing adds this
        automatically now.
        """

        name = identity.owner()

        if self.level == "formal":

            return f"Certainly, {name}." if name else "Certainly."

        if self.level == "friendly":

            return f"Sure, {name}." if name else "Sure."

        return f"Hey, {name}." if name else "Hey."

    # ------------------------------------------------------------------
    def tone(self):
        """Familiarity expressed as a tone hint for the style controller."""

        if self.level == "formal":

            return "professional"

        if self.level == "friendly":

            return "friendly"

        return "casual"

    def data(self):

        return {

            "level": self.level,

            "talks": self.talks

        }


adaptive = AdaptiveEngine()
