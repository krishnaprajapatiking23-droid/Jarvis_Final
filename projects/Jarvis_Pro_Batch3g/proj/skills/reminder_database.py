import json
import os

FILE = "data/reminders.json"


def load_reminders():

    if not os.path.exists(FILE):
        return []

    with open(FILE, "r") as file:
        return json.load(file)


def save_reminders(reminders):

    with open(FILE, "w") as file:
        json.dump(reminders, file, indent=4)


def add_reminder(task):

    reminders = load_reminders()

    reminder = {
        "task": task,
        "status": "Pending",
        "completed": False
    }

    reminders.append(reminder)

    save_reminders(reminders)


def delete_reminder(index):

    reminders = load_reminders()

    if index < 0 or index >= len(reminders):
        return False

    reminders.pop(index)

    save_reminders(reminders)

    return True


def complete_reminder(index):

    reminders = load_reminders()

    if index < 0 or index >= len(reminders):
        return False

    reminders[index]["status"] = "Completed"
    reminders[index]["completed"] = True

    save_reminders(reminders)

    return True


def clear_reminders():

    save_reminders([])