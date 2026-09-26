from brains_v2.agents.base_agent import Agent

from memory.semantic_memory import semantic_memory
from memory.memory_search import memory_search
from memory.memory_ranker import memory_ranker


class MemoryAgent(Agent):

    name = "Memory Agent"

    description = "Stores, searches and recalls memories."

    priority = 90

    KEYWORDS = {

        "remember",
        "memory",
        "recall",
        "forget",
        "store",
        "save",
        "who am i",
        "my name",
        "favorite",
        "favourite"

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

    def plan(self, command):

        return [

            "Analyse memory request",
            "Search memory",
            "Store or Recall",
            "Return result"

        ]

    def execute(self, command):

        try:

            semantic_memory.store(command)

        except Exception:

            pass

        try:

            result = memory_search.search(command)

            if result:

                return self.success(result)

        except Exception:

            pass

        try:

            ranked = memory_ranker.rank(command)

            if ranked:

                return self.success(ranked)

        except Exception:

            pass

        return {

            "success": False,

            "agent": self.name,

            "reply": "No related memory found."

        }

    def success(self, result):

        return {

            "success": True,

            "agent": self.name,

            "plan": self.plan(""),

            "reply": result

        }

    def verify(self, result):

        return result.get("success", False)

    def learn(self, command, result):

        pass


agent = MemoryAgent()