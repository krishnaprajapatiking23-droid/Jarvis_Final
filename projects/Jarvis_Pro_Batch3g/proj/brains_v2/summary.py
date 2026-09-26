class SummaryEngine:

    def __init__(self):

        self.summary = ""

    def update(self, dialogue):

        if not dialogue:

            self.summary = "No conversation."

            return

        recent = dialogue[-6:]

        text = []

        for item in recent:

            text.append(item["text"])

        self.summary = " | ".join(text)

    def get(self):

        return self.summary


summary = SummaryEngine()