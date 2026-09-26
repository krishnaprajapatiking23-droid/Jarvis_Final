from brains_v2.core.pipeline import pipeline
from brains_v2.ai.intent_engine import detect


class BrainEngine:

    def process(self, command):

        intent = detect(command)

        data = {
            "command": command,
            "intent": intent
        }

        return pipeline.execute(data)


brain_engine = BrainEngine()