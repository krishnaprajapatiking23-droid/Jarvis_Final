from brains_v2.llm.manager import ask


class LLMController:

    def process(self, command, context=""):

        return ask(command, context)


llm_controller = LLMController()