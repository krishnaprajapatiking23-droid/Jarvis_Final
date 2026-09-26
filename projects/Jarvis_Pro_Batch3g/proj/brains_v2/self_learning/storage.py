import json
import os

DATA_FILE = "data/experience.json"


def load_data():
    if not os.path.exists(DATA_FILE):
        return {
            "commands": [],
            "statistics": {},
            "mistakes": [],
            "successes": [],
            "predictions": {},
            "habits": {}
        }

    with open(DATA_FILE, "r", encoding="utf-8") as file:
        return json.load(file)


def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=4)