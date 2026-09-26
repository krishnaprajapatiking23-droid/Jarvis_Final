"""
Memory Storage
"""

from .memory_manager import memory_intent


class Storage:

    def save(self, category, key, value):

        return memory_intent.remember(

            category,

            key,

            value

        )

    def load(self, key):

        return memory_intent.recall(key)

    def delete(self, key):

        return memory_intent.forget(key)


storage = Storage()