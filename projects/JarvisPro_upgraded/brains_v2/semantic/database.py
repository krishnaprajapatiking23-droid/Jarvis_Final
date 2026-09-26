import json
import os


class SemanticMemory:

    FILE = "brains_v2/semantic/memory.json"

    def __init__(self):

        self.memories = []

        self.load()

    def load(self):

        if os.path.exists(self.FILE):

            with open(self.FILE, "r", encoding="utf-8") as f:

                self.memories = json.load(f)

    def save(self):

        with open(self.FILE, "w", encoding="utf-8") as f:

            json.dump(
                self.memories,
                f,
                indent=4,
                ensure_ascii=False
            )

    def add(self, text):

        if text not in self.memories:

            self.memories.append(text)

            self.save()

    def all(self):

        return self.memories


memory = SemanticMemory()