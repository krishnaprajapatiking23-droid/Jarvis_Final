"""
Embedding Engine
Jarvis Version 2
"""


class EmbeddingEngine:

    def __init__(self):

        pass

    def encode(self, text):

        return text.lower().split()

    def similarity(self, a, b):

        sa = set(self.encode(a))

        sb = set(self.encode(b))

        if not sa or not sb:

            return 0.0

        return len(sa & sb) / len(sa | sb)


# This object is imported by __init__.py
embeddings = EmbeddingEngine()