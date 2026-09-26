"""
Main Brain
"""

from .router import brain
from .planner import planner
from .context import context


class JarvisBrain:

    def think(self, command):

        plan = planner.create_plan(command)

        result = brain.process(command)

        if isinstance(result, dict):

            reply = result.get("message", "Done")

        else:

            reply = str(result)

        context.add(command, reply)

        return {

            "plan": plan,

            "reply": reply

        }


jarvis = JarvisBrain()