from brains_v2.llm.manager import ask


class LLMService:

    def process(self, data):

        reply = ask(data["command"])

        return {
            "reply": reply
        }


llm_service = LLMService()