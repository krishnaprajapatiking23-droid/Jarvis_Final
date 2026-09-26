"""
Wake Word Engine
"""

WAKE_WORDS = [

    "jarvis",

    "hey jarvis",

    "ok jarvis"

]


class WakeWord:

    def detect(self, text):

        if not text:

            return False

        text = text.lower().strip()

        for wake in WAKE_WORDS:

            if wake in text:

                return True

        return False


wakeword = WakeWord()