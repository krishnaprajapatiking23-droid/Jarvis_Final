from core.nlp import contains_any

from skills.note_database import (
    load_notes,
    add_note,
    delete_note,
)


def process_notes(command):

    text = command.lower().strip()

    # ==========================
    # Add Note
    # ==========================
    if text.startswith("take a note"):

        note = command[11:].strip(": ").strip()

        add_note(note)

        return "📝 Note saved."

    # ==========================
    # Show Notes
    # ==========================
    if (
    (
        "show" in text
        or "display" in text
        or "list" in text
        or "read" in text
    )
    and
    ("note" in text or "notes" in text)
):

        notes = load_notes()

        if not notes:
            return "No notes found."

        answer = "📝 Your Notes\n\n"

        for i, note in enumerate(notes, 1):

            answer += f"{i}. {note['note']}\n"

        return answer

    # ==========================
    # Delete Note
    # ==========================
    if text.startswith("delete note"):

        try:

            index = int(text.split()[-1]) - 1

            if delete_note(index):
                return "🗑 Note deleted."

            return "Invalid note number."

        except:
            return "Usage: delete note 1"

    return None