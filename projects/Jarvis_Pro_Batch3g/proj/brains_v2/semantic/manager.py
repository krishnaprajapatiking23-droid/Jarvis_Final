from brains_v2.semantic.database import memory
from brains_v2.semantic.search import search


def remember(text):

    memory.add(text)


def recall(query):

    return search(query)