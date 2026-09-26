import re
from brains_v3.intent_memory import intent_memory
from brains_v3.ai_intent import ai_intent


class IntentEngine:

    def detect(self, command):

        text = command.lower().strip()

        saved = intent_memory.search(text)

        if saved:

            return {
                "intent": saved,
                "confidence": 1.0,
                "source": "memory"
            }

        # -------------------------
        # Open App
        # -------------------------

        if any(word in text for word in [
            "open",
            "launch",
            "run",
            "start"
        ]):

            return {
                "intent": "open_app",
                "confidence": 0.95,
                "source": "rules"
            }

        # -------------------------
        # Website
        # -------------------------

        if any(word in text for word in [
            "website",
            "google",
            "youtube",
            "search"
        ]):

            return {
                "intent": "web",
                "confidence": 0.95,
                "source": "rules"
            }

        # -------------------------
        # Notes
        # -------------------------

        if "note" in text:

            return {
                "intent": "notes",
                "confidence": 0.95,
                "source": "rules"
            }

        # -------------------------
        # Reminder
        # -------------------------

        if "remind" in text:

            return {
                "intent": "reminder",
                "confidence": 0.95,
                "source": "rules"
            }

        # -------------------------
        # Memory
        # -------------------------

        if any(word in text for word in [
            "remember",
            "recall",
            "who am i",
            "my name"
        ]):

            return {
                "intent": "memory",
                "confidence": 0.95,
                "source": "rules"
            }

        # -------------------------
        # Exit
        # -------------------------

        if text in [
            "exit",
            "quit",
            "bye"
        ]:

            return {
                "intent": "exit",
                "confidence": 1.0,
                "source": "rules"
            }

        # -------------------------
        # Unknown
        # -------------------------

        result = ai_intent.detect(command)

        intent_memory.remember(
            command,
            result["intent"]
        )

        return {
            "intent": result["intent"],
            "confidence": 0.80,
            "source": "ai"
        }

intent_engine = IntentEngine()