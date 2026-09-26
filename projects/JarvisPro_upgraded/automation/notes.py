"""
Notes Module
"""
from pathlib import Path
from datetime import datetime

NOTES_FOLDER = Path("data/notes")
NOTES_FOLDER.mkdir(parents=True, exist_ok=True)


def save_note(command):

    text = command.strip()

    prefixes = [
        "note",
        "remember",
        "save",
        "save this",
        "note that"
    ]

    lower = text.lower()

    for prefix in prefixes:
        if lower.startswith(prefix):
            text = text[len(prefix):].strip()
            break

    if not text:
        return {
            "status": "FAILED",
            "reply": "I couldn't find anything to save."
        }

    file = NOTES_FOLDER / "notes.txt"

    with open(file, "a", encoding="utf-8") as f:
        f.write(f"[{datetime.now()}] {text}\n")

    return {
        "status": "SUCCESS",
        "reply": "Your note has been saved."
    }