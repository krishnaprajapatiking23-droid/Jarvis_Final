from memory.semantic_memory import semantic_memory
from memory.memory_ranker import memory_ranker


class MemorySearch:

    def search(self, query, limit=5):

        semantic_results = semantic_memory.search(query, threshold=0.0)

        memories = []

        for item in semantic_results:

            memory = item["memory"].copy()

            memory.setdefault("frequency", 1)
            memory.setdefault("importance", 1)
            memory.setdefault("confidence", 1.0)

            memories.append(memory)

        ranked = memory_ranker.rank(query, memories)

        return ranked[:limit]

    def best_match(self, query):

        results = self.search(query, limit=1)

        if results:

            return results[0]

        return None

    def remember(self, topic, content, tags=None):

        return semantic_memory.add(
            topic=topic,
            content=content,
            tags=tags
        )

    def forget(self, topic):

        return semantic_memory.delete(topic)

    def all(self):

        return semantic_memory.all()


memory_search = MemorySearch()