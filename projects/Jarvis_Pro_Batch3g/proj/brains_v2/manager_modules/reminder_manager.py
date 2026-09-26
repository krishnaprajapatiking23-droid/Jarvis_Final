from brains_v2.reminders.reminders import add, show, mutate, parse_time


def process(command):
    text = " ".join(str(command or "").split())
    low = text.lower()
    if "remind" not in low and "reminder" not in low:
        return None
    if low.startswith("list reminder") or low.startswith("show reminder"):
        return show()
    for operation in ("cancel", "delete", "complete"):
        prefix = operation + " reminder "
        if low.startswith(prefix):
            token = low[len(prefix):].strip()
            return f"Reminder {operation}d." if mutate(token, operation) else "Reminder not found."
    if low.startswith("update reminder "):
        rest = text[len("update reminder "):].split(maxsplit=1)
        if len(rest) != 2:
            return "Provide the reminder number and replacement text."
        return "Reminder updated." if mutate(rest[0], "update", rest[1]) else "Reminder not found."
    due = parse_time(text)
    if due:
        title = text
        for prefix in ("remind me to ", "remind me "):
            if title.lower().startswith(prefix):
                title = title[len(prefix):]
                break
        marker = title.lower().rfind(" in ")
        if marker >= 0:
            title = title[:marker]
        return add(title, due)
    return "Please include a reminder time."
