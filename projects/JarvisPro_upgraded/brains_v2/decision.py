"""
Decision Engine
"""


class DecisionEngine:

    def execute(self, command):

        command = command.lower()

        if (
            "open" in command
            or "youtube" in command
            or "google" in command
            or "chrome" in command
            or "calculator" in command
            or "notepad" in command
            or "desktop" in command
            or "screenshot" in command
        ):
            return "OPEN"

        return "CHAT"


decision = DecisionEngine()


def decide(command):
    return decision.execute(command)