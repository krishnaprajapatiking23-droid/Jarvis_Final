"""
==========================================
JARVIS PRO
Reply controller
==========================================

Final stop before a reply leaves the brain.

This controller used to make every answer look the same: it appended an
automatic follow-up question, wrapped the text in a random starter and
ending, then glued a fixed "Certainly, <name>." prefix on top.  All of
that is gone.  Wording is now decided per turn by the response planner
and style controller; this layer only cleans up stock assistant phrases
and keeps the familiarity tracker updated.
"""

from brains_v2.adaptive import adaptive
from brains_v2.personality_engine import personality
from brains_v2.response import generate
from brains_v2.style import style
from conversation import repetition_detector


class ReplyController:

    def process(self, route, result, reply):

        if reply is None:
            reply = generate(result)

        if not isinstance(reply, str):
            reply = str(reply)

        # Personality stays stable; only the tone hint travels onward.
        try:
            data = personality.data()
        except Exception:
            data = {}

        style.update(data)
        adaptive.update(data)

        reply = style.apply(reply)

        # Strip "Certainly!", "Hope this helps!" and reasoning traces.
        reply = repetition_detector.strip_cliches(reply)

        return reply.strip()


reply_controller = ReplyController()
