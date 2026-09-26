"""
Background Task Executor
"""

from automation.notes import save_note
from automation.reminders import add_reminder

class BackgroundExecutor:

    def execute(self, command):

        text = command.lower()

        # ------------------------
        # NOTES
        # ------------------------

        if text.startswith("note"):

            return save_note(command)

        if text.startswith("remember"):

            return save_note(command)

        return {
            "status": "UNKNOWN",
            "reply": "Background task not supported."
        }
    
        if text.startswith("remind"):

           reminder = command.replace("remind", "", 1).strip()

        return add_reminder(reminder)


background_executor = BackgroundExecutor()