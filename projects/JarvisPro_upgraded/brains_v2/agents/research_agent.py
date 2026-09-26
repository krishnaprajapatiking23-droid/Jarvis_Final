from brains_v2.agents.base_agent import Agent
from brains_v2.llm.manager import ask


class ResearchAgent(Agent):

    name = "Research Agent"

    description = "Researches, explains, compares and summarizes."

    priority = 90

    KEYWORDS = {

        "research",
        "find",
        "search",
        "analyse",
        "analyze",
        "compare",
        "comparison",
        "difference",
        "advantages",
        "disadvantages",
        "pros",
        "cons",
        "explain",
        "summary",
        "summarize",
        "learn",
        "study",
        "history",
        "science",
        "technology",
        "business",
        "market",
        "information",
        "details",
        "review",
        "report"
    }

    def can_handle(self, command):

        text = command.lower()

        return any(word in text for word in self.KEYWORDS)

    def score(self, command):

        text = command.lower()

        score = 0

        for word in self.KEYWORDS:

            if word in text:
                score += 10

        return min(score, 100)

    def plan(self, command):

        return [

            "Understand topic",
            "Collect information",
            "Analyse",
            "Generate answer",
            "Verify"

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
            "reply": "Research model is unavailable."

        }

    def verify(self, result):

        return result.get("success", False)

    def learn(self, command, result):

        pass


agent = ResearchAgent()