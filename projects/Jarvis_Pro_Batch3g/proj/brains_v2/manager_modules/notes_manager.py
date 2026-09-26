from brains_v2.trace import trace
from brains_v2.intents.note_intent import detect
from brains_v2.notes.notes import (
    add_note,
    show_notes,
    read_note,
    delete_note,
    clear_notes,
)


def process(command):

    trace(">>> NOTES MANAGER CALLED <<<")

    note = detect(command)

    trace(note)

    if not note:
        return None

    if note["type"] == "add_note":
        return {
            "reply": add_note(note["content"])
        }

    if note["type"] == "show_notes":
        return {
            "reply": show_notes()
        }

    if note["type"] == "read_note":
        return {
            "reply": read_note(note["index"])
        }

    if note["type"] == "delete_note":
        return {
            "reply": delete_note(note["index"])
        }

    if note["type"] == "clear_notes":
        return {
            "reply": clear_notes()
        }

    return None