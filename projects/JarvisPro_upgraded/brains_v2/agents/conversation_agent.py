from brains_v2.agents.base_agent import Agent
from brains_v2.llm.manager import ask


class ConversationAgent(Agent):

    name = "Conversation Agent"

    description = "Handles natural conversations."

    priority = 10

    CHAT_KEYWORDS = {

        "hello",
        "hi",
        "hey",
        "thanks",
        "thank you",
        "good morning",
        "good night",
        "how are you",
        "what's up",
        "who are you",
        "your name",
        "talk",
        "chat",
        "friend"

    }

    def can_handle(self, command):

        return True

    def score(self, command):

        text = command.lower()

        score = 5

        for word in self.CHAT_KEYWORDS:

            if word in text:
                score += 15

        return min(score, 40)

    def plan(self, command):

        return [

            "Understand user",
            "Generate natural reply",
            "Maintain conversation"

        ]

    def execute(self, command):

        reply = ask(command)

        if reply:

            return {

                "success": True,
                "agent": self.name,
                "plan": self.plan(command),
                "reply": reply

            }

        return {

            "success": False,
            "agent": self.name,
            "reply": "I couldn't generate a response."

        }

    def verify(self, result):

        return result.get("success", False)

    def learn(self, command, result):

        pass


agent = ConversationAgent()