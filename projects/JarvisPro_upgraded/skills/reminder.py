from skills.reminder_database import (
    load_reminders,
    add_reminder,
    delete_reminder,
    complete_reminder,
    clear_reminders,
)


def process_reminder(command):

    text = command.lower().strip()

    # ==========================
    # Add Reminder
    # ==========================
    if text.startswith("remind me to"):

        task = command[12:].strip()

        add_reminder(task)

        return f"✅ Reminder saved: {task}"

    # ==========================
    # Show Reminders
    # ==========================
    if text == "show reminders":

        reminders = load_reminders()

        if not reminders:
            return "You don't have any reminders."

        answer = "📋 Your Reminders:\n\n"

        for i, reminder in enumerate(reminders, 1):

            status = "✅" if reminder["completed"] else "⏳"

            answer += (
                f"{i}. {status} "
                f"{reminder['task']} "
                f"({reminder['status']})\n"
            )

        return answer

    # ==========================
    # Complete Reminder
    # ==========================
    if text.startswith("complete reminder"):

        try:

            index = int(text.split()[-1]) - 1

            if complete_reminder(index):
                return "✅ Reminder completed."

            return "❌ Invalid reminder number."

        except:
            return "❌ Usage: complete reminder 1"

    # ==========================
    # Delete Reminder
    # ==========================
    if text.startswith("delete reminder"):

        try:

            index = int(text.split()[-1]) - 1

            if delete_reminder(index):
                return "🗑 Reminder deleted."

            return "❌ Invalid reminder number."

        except:
            return "❌ Usage: delete reminder 1"

    # ==========================
    # Clear All Reminders
    # ==========================
    if text == "clear reminders":

        clear_reminders()

        return "🗑 All reminders cleared."

    return None