from brains_v2.agents.base_agent import Agent
from brains_v2.llm.manager import ask


class CodingAgent(Agent):

    name = "Coding Agent"

    description = "Professional software engineering agent."

    priority = 95

    KEYWORDS = {

        "python",
        "code",
        "coding",
        "program",
        "script",
        "java",
        "javascript",
        "c++",
        "c#",
        "html",
        "css",
        "sql",
        "bug",
        "debug",
        "fix",
        "error",
        "exception",
        "project",
        "api",
        "class",
        "function",
        "method",
        "algorithm",
        "json",
        "database",
        "flask",
        "django",
        "fastapi",
        "react",
        "node",
        "git",
        "github",
        "jarvis"
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

            "Understand request",

            "Analyse code/problem",

            "Generate solution",

            "Verify solution"

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

            "reply": "Coding model is unavailable."

        }

    def verify(self, result):

        return result.get("success", False)

    def learn(self, command, result):

        pass


agent = CodingAgent()