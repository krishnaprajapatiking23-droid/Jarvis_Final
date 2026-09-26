"""
Jarvis AI Assistant
"""

from .router import ai_router


class Assistant:

    def ask(self, command):

        result = ai_router.process(command)

        if isinstance(result, dict):

            return result.get(
                "message",
                "Done."
            )

        return str(result)


assistant = Assistant()