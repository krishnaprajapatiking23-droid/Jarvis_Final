import re


def detect(command: str):

    command = command.strip()
    lower = command.lower()

    # -----------------------------------
    # Add reminder
    # Example:
    # remind me tomorrow at 5 pm to study
    # remind me at 17:00 to study
    # -----------------------------------

    pattern = (
        r"remind me "
        r"(?:tomorrow\s+)?"
        r"at\s+"
        r"(\d{1,2})"
        r"(?::(\d{2}))?"
        r"\s*(am|pm)?"
        r"\s+to\s+"
        r"(.+)"
    )

    match = re.match(pattern, lower)

    if match:

        hour = int(match.group(1))
        minute = match.group(2) or "00"
        period = match.group(3)
        title = match.group(4).strip()

        # -----------------------------------
        # Convert AM/PM to 24-hour time
        # -----------------------------------

        if period == "pm" and hour != 12:
            hour += 12

        elif period == "am" and hour == 12:
            hour = 0

        time = f"{hour:02d}:{minute}"

        return {
            "type": "add_reminder",
            "title": title,
            "time": time
        }

    # -----------------------------------
    # Show reminders
    # -----------------------------------

    if lower == "show reminders":

        return {
            "type": "show_reminders"
        }

    return None