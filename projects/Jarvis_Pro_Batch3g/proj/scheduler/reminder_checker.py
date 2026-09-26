from skills.reminder_database import load_reminders, save_reminders

from scheduler.clock import current_date, current_time


def check_reminders():

    reminders = load_reminders()

    today = current_date()
    now = current_time()

    notifications = []

    changed = False

    for reminder in reminders:

        # Compatibility with old reminders
        reminder.setdefault("completed", reminder.get("done", False))
        reminder.setdefault("notified", False)
        reminder.setdefault("date", today)

        if reminder["completed"]:
            continue

        if reminder["notified"]:
            continue

        if (
            reminder["date"] == today
            and reminder["time"] == now
        ):

            notifications.append(reminder)

            reminder["notified"] = True

            changed = True

    if changed:
        save_reminders(reminders)

    return notifications