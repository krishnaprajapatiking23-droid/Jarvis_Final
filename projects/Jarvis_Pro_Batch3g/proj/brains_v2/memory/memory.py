import json
import os

MEMORY_FILE = "data/memory.json"


def load_memory():
    if not os.path.exists(MEMORY_FILE):
        return {
            "facts": [],
            "preferences": [],
            "goals": [],
            "people": [],
            "events": []
        }

    with open(MEMORY_FILE, "r") as f:
        return json.load(f)


def save_memory(memory):
    with open(MEMORY_FILE, "w") as f:
        json.dump(memory, f, indent=4)


def remember(category, text):

    memory = load_memory()

    if category not in memory:
        memory[category] = []

    memory[category].append(text)

    save_memory(memory)

    return f"I'll remember that {text}."


def recall(category):

    memory = load_memory()

    if category not in memory:
        return None

    if not memory[category]:
        return None

    return memory[category]

def update_profile(field, value):

    memory = load_memory()

    memory["profile"][field] = value

    save_memory(memory)

    return f"I'll remember your {field}."


def get_profile(field):

    memory = load_memory()

    return memory["profile"].get(field, "")

def add_person(name):

    memory = load_memory()

    if name not in memory["people"]:
        memory["people"].append(name)

    save_memory(memory)

    return f"I'll remember {name}."


def get_people():

    memory = load_memory()

    return memory["people"]