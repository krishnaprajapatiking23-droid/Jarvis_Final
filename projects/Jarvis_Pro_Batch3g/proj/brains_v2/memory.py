class ShortMemory:

    def __init__(self):

        self.history = []

        self.max_history = 20

    def add(self, command, reply):

        self.history.append({

            "command": command,

            "reply": reply

        })

        if len(self.history) > self.max_history:

            self.history.pop(0)

    def last(self):

        if not self.history:

            return None

        return self.history[-1]

    def all(self):

        return self.history


memory = ShortMemory()