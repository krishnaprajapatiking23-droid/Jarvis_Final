import random


FOLLOWUPS = [

    "What would you like to do next?",

    "Is there anything else you need?",

    "What's the next step?",

    "Shall we continue?",

    "What are we building next?",

    "Anything else on your mind?"

]


class FollowUpEngine:

    def __init__(self):

        self.previous_topic = ""

    def understand(self, command):

        command = str(command).strip()

        if not command:

            return {

                "understood": False,

                "topic": "",

                "reference": "",

                "follow_up": ""

            }

        text = command.lower()

        reference_words = [

            "it",

            "this",

            "that",

            "them",

            "they",

            "he",

            "she"

        ]

        is_reference = any(

            word in text.split()

            for word in reference_words

        )

        if is_reference:

            if not self.previous_topic:

                return {

                    "understood": False,

                    "topic": "",

                    "reference": "",

                    "follow_up": ""

                }

            return {

                "understood": True,

                "topic": self.previous_topic,

                "reference": self.previous_topic,

                "follow_up": command

            }

        topic = self._extract_topic(text)

        if topic:

            self.previous_topic = topic

            return {

                "understood": True,

                "topic": topic,

                "reference": "",

                "follow_up": ""

            }

        return {

            "understood": False,

            "topic": "",

            "reference": "",

            "follow_up": ""

        }

    def _extract_topic(self, text):

        if "python website" in text:

            return "Python website"

        if "javascript website" in text:

            return "JavaScript website"

        if "python project" in text:

            return "Python project"

        if "website" in text:

            return "website"

        if "python" in text:

            return "Python"

        return ""


def next_question():

    return random.choice(FOLLOWUPS)


followup = FollowUpEngine()