"""
Reminder Module
"""

import json
from pathlib import Path
from datetime import datetime

DATA = Path("data")
DATA.mkdir(exist_ok=True)

FILE = DATA / "reminders.json"


def load():

    if not FILE.exists():
        return []

    with open(FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save(data):

    with open(FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)


def add_reminder(text):

    reminders = load()

    reminders.append({

        "text": text,

        "created": str(datetime.now()),

        "completed": False

    })

    save(reminders)

    return {

        "status": "SUCCESS",

        "reply": "Reminder added."

    }