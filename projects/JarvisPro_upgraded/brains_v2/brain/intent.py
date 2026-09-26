"""
Intent Detection
"""

class IntentDetector:

    def detect(self, command):

        command = command.lower()

        if any(x in command for x in [
            "open",
            "launch",
            "start"
        ]):
            return "automation"

        if any(x in command for x in [
            "remember",
            "save"
        ]):
            return "memory_save"

        if any(x in command for x in [
            "what",
            "who",
            "where",
            "when"
        ]):
            return "question"

        return "chat"


intent = IntentDetector()