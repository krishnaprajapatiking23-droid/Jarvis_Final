"""
Conversation Context
"""


class Context:

    def __init__(self):

        self.history = []

    def add(self, user, assistant):

        self.history.append({

            "user": user,

            "assistant": assistant

        })

        if len(self.history) > 20:

            self.history.pop(0)

    def get(self):

        return self.history


context = Context()