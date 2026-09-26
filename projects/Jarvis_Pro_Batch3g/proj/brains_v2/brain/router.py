"""
Brain Router
"""

from .intent import intent
from .chat import chat
from brains_v2.decision import decision
from brains_v2.memory import memory_intent


class BrainRouter:

    def process(self, command):

        task = intent.detect(command)

        if task == "automation":

            return decision.execute(command)

        elif task == "memory_save":

            try:

                text = command.replace("remember", "").strip()

                if " is " in text:

                    key, value = text.split(" is ", 1)

                elif "=" in text:

                    key, value = text.split("=", 1)

                else:

                    return {
                        "success": False,
                        "message": "Use: remember X is Y"
                    }

                memory_intent.remember(
                    "personal",
                    key.strip(),
                    value.strip()
                )

                return {
                    "success": True,
                    "message": "Memory saved."
                }

            except Exception as e:

                return {
                    "success": False,
                    "message": str(e)
                }

        elif task == "question":

            text = command.lower()

            if "company" in text:

                value = memory_intent.recall("company")

                if value:

                    return {
                        "success": True,
                        "message": value
                    }

            if "name" in text:

                value = memory_intent.recall("name")

                if value:

                    return {
                        "success": True,
                        "message": value
                    }

        return {
            "success": True,
            "message": chat.reply(command)
        }


brain = BrainRouter()