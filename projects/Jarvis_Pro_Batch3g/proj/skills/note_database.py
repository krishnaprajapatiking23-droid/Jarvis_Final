import json
import os

FILE = "data/notes.json"


def load_notes():

    if not os.path.exists(FILE):
        return []

    with open(FILE, "r") as file:
        return json.load(file)


def save_notes(notes):

    with open(FILE, "w") as file:
        json.dump(notes, file, indent=4)


def add_note(text):

    notes = load_notes()

    notes.append({
        "note": text
    })

    save_notes(notes)


def delete_note(index):

    notes = load_notes()

    if index < 0 or index >= len(notes):
        return False

    notes.pop(index)

    save_notes(notes)

    return True