class Personality:

    def __init__(self):

        self.mode = "friendly"

        self.mood = "neutral"

    def update(self, emotion):

        if emotion == "happy":

            self.mode = "friendly"

        elif emotion == "focused":

            self.mode = "professional"

        elif emotion == "thinking":

            self.mode = "analytical"

        else:

            self.mode = "normal"

        self.mood = emotion

    def data(self):

        return {

            "mode": self.mode,

            "mood": self.mood

        }


personality = Personality()