from brains_v2.intents.reminder_intent import detect as detect_reminder
from brains_v2.reminders.reminders import add, show


class ReminderController:

    def process(self, command):

        reminder = detect_reminder(command)

        if not reminder:
            return None

        if reminder["type"] == "add_reminder":

            return {
                "reply": add(
                    reminder["title"],
                    reminder["time"]
                )
            }

        if reminder["type"] == "show_reminders":

            return {
                "reply": show()
            }

        return None


reminder_controller = ReminderController()