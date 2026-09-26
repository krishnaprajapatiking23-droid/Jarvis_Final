# psychology/database.py

import json
import os

DB_FILE = "data/psychology.json"


def load_data():
    if not os.path.exists(DB_FILE):
        return {}

    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_data(data):
    os.makedirs("data", exist_ok=True)

    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)


def get_owner():
    data = load_data()
    return data.get("owner", {})


def save_owner(report):
    data = load_data()
    data["owner"] = report
    save_data(data)