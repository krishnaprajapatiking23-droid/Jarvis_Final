def detect(command: str):
    command = command.strip()

    lower = command.lower()

    if lower.startswith("note ") or lower.startswith("add note "):
        return {
            "type": "add_note",
            "content": command[9:].strip() if lower.startswith("add note ") else command[5:].strip()
        }

    if lower == "show notes":
        return {
            "type": "show_notes"
        }

    if lower.startswith("read note "):
        try:
            return {
                "type": "read_note",
                "index": int(lower.replace("read note ", ""))
            }
        except ValueError:
            return None

    if lower.startswith("delete note "):
        try:
            return {
                "type": "delete_note",
                "index": int(lower.replace("delete note ", ""))
            }
        except ValueError:
            return None

    if lower == "clear notes":
        return {
            "type": "clear_notes"
        }

    return None