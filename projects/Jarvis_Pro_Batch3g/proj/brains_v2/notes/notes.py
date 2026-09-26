import json
import os

NOTES_FILE = "data/notes.json"


def load_notes():
    if not os.path.exists(NOTES_FILE):
        return []

    with open(NOTES_FILE, "r") as file:
        return json.load(file)


def save_notes(notes):
    with open(NOTES_FILE, "w") as file:
        json.dump(notes, file, indent=4)


def add_note(note):
    notes = load_notes()
    notes.append({"note": note})
    save_notes(notes)
    return "Note saved."


def show_notes():
    notes = load_notes()

    if not notes:
        return "No notes found."

    result = ""

    for i, note in enumerate(notes, start=1):
        result += f"{i}. {note['note']}\n"

    return result.strip()

def read_note(index):
    notes = load_notes()

    if index < 1 or index > len(notes):
        return "Invalid note number."

    return notes[index - 1]["note"]

def delete_note(index):
    notes = load_notes()

    if index < 1 or index > len(notes):
        return "Invalid note number."

    notes.pop(index - 1)

    save_notes(notes)

    return "Note deleted."

def clear_notes():
    save_notes([])
    return "All notes cleared."