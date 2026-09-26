import json
import os

PROJECT_FILE = "data/projects.json"


def load_projects():

    if not os.path.exists(PROJECT_FILE):
        return {}

    with open(PROJECT_FILE, "r", encoding="utf-8") as file:
        return json.load(file)


def save_projects(projects):

    os.makedirs("data", exist_ok=True)

    with open(PROJECT_FILE, "w", encoding="utf-8") as file:
        json.dump(projects, file, indent=4)