from memory.memory_engine import process_memory


class MemoryService:

    def process(self, data):

        intent = data["intent"]

        if intent["intent"] in ["remember", "recall"]:

            result = process_memory(data["command"])

            if result:

                return {
                    "reply": result
                }

        return data


memory_service = MemoryService()