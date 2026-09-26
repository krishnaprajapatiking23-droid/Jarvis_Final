class DialogueMemory:

    def __init__(self):

        self.messages = []

        self.max_size = 50

    def add(self, role, text):

        self.messages.append({

            "role": role,

            "text": text

        })

        if len(self.messages) > self.max_size:

            self.messages.pop(0)

    def recent(self, count=10):

        return self.messages[-count:]

    def clear(self):

        self.messages.clear()


dialogue_memory = DialogueMemory()