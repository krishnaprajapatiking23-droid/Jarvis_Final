"""
Conversation Context
"""


class Context:

    def __init__(self):

        self.history = []

        self.topic = None

        self.last_command = None


context = Context()

# Backward-compatible name used by older conversation modules
CONTEXT = context