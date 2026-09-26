from brains_v2.agents.base_agent import Agent
from brains_v2.config import settings


class SecurityAgent(Agent):

    name = "Security Agent"

    description = "Protects Jarvis and validates sensitive commands."

    priority = 99

    KEYWORDS = {

        "shutdown",
        "restart",
        "delete",
        "remove",
        "format",
        "security",
        "permission",
        "admin",
        "password",
        "owner",
        "lock",
        "unlock"

    }

    PROTECTED_COMMANDS = {

        "shutdown",
        "restart",
        "delete",
        "format",
        "factory reset",
        "erase"

    }

    def can_handle(self, command):

        text = command.lower()

        return any(word in text for word in self.KEYWORDS)

    def score(self, command):

        text = command.lower()

        score = 0

        for word in self.KEYWORDS:

            if word in text:
                score += 15

        return min(score, 100)

    def execute(self, command):

        text = command.lower()

        for cmd in self.PROTECTED_COMMANDS:

            if cmd in text:

                return {

                    "success": True,

                    "agent": self.name,

                    "secure": True,

                    "allowed": True,

                    "owner": settings.get("owner", "Unknown"),

                    "reply": f"Protected command detected: {cmd}"

                }

        if "who is the owner" in text:

            return {

                "success": True,

                "agent": self.name,

                "reply": settings.get("owner", "Unknown")

            }

        if "security status" in text:

            return {

                "success": True,

                "agent": self.name,

                "reply": "Security system is operational."

            }

        return {

            "success": False,

            "agent": self.name,

            "reply": None

        }

    def verify(self, result):

        return result.get("success", False)

    def learn(self, command, result):

        pass


agent = SecurityAgent()