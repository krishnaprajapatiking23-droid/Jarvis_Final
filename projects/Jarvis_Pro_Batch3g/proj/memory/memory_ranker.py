import time
from difflib import SequenceMatcher


class MemoryRanker:

    def rank(self, query, memories=None):

        if memories is None:
            memories = []

        ranked = []

        current_time = time.time()

        for memory in memories:

            score = 0.0

            topic = memory.get("topic", "")
            content = memory.get("content", "")
            tags = memory.get("tags", [])

            similarity = max(
                self.similarity(query, topic),
                self.similarity(query, content),
                max(
                    [
                        self.similarity(query, tag)
                        for tag in tags
                    ],
                    default=0
                )
            )

            score += similarity * 60

            frequency = memory.get("frequency", 1)
            score += min(frequency, 20)

            importance = memory.get("importance", 1)
            score += importance * 5

            timestamp = memory.get("timestamp")

            if timestamp:

                age_days = (current_time - timestamp) / 86400

                recency = max(0, 10 - age_days)

                score += recency

            confidence = memory.get("confidence", 1.0)

            score += confidence * 10

            ranked.append({

                "score": round(score, 2),

                "memory": memory

            })

        ranked.sort(
            key=lambda item: item["score"],
            reverse=True
        )

        return ranked


memory_ranker = MemoryRanker()