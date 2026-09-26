"""
LLM Router
"""

from brains_v2.decision import decision
from brains_v2.llm import chat_ai
from brains_v2.memory import memory_intent


class AIRouter:

    def process(self, command):

        cmd = command.lower()

        # Automation Commands
        if any(x in cmd for x in [
            "open",
            "close",
            "launch",
            "shutdown",
            "restart",
            "screenshot",
            "desktop"
        ]):
            return decision.execute(command)

        # Memory Save
        if cmd.startswith("remember"):

            text = command[8:].strip()

            if " is " in text:

                key, value = text.split(" is ", 1)

                memory_intent.remember(
                    "personal",
                    key.strip(),
                    value.strip()
                )

                return {
                    "success": True,
                    "message": "Memory saved."
                }

        # Memory Recall
        if cmd.startswith("what is"):

            key = cmd.replace("what is", "").strip()

            value = memory_intent.recall(key)

            if value:

                return {
                    "success": True,
                    "message": value
                }

        # AI Chat
        return {
            "success": True,
            "message": chat_ai.chat(command)
        }


ai_router = AIRouter()