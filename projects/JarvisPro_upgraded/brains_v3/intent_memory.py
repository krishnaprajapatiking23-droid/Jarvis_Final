import json
import os


FILE = "brains_v3/data/intents.json"


class IntentMemory:

    def __init__(self):

        os.makedirs("brains_v3/data", exist_ok=True)

        if not os.path.exists(FILE):

            with open(FILE, "w") as f:

                json.dump({}, f)

    def load(self):

        with open(FILE, "r") as f:

            return json.load(f)

    def save(self, data):

        with open(FILE, "w") as f:

            json.dump(data, f, indent=4)

    def remember(self, phrase, intent):

        data = self.load()

        data[phrase.lower()] = intent

        self.save(data)

    def search(self, command):

        data = self.load()

        command = command.lower()

        for phrase in data:

            if phrase in command:

                return data[phrase]

        return None


intent_memory = IntentMemory()