import json
import os
import sys


def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    return os.path.join(base_path, relative_path)


def load():
    path = resource_path("config/settings.json")

    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


settings = load()