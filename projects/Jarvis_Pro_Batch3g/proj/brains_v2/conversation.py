class Conversation:

    def __init__(self):

        self.messages = []

    def add(self, user, jarvis):

        self.messages.append({

            "user": user,

            "jarvis": jarvis

        })

    def last(self):

        if not self.messages:

            return None

        return self.messages[-1]

    def history(self):

        return list(self.messages)


conversation = Conversation()