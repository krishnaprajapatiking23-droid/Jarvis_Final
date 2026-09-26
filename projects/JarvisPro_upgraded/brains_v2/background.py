"""
Background Execution Manager
"""


BACKGROUND_TASKS = {

    "note",

    "remember",

    "save",

    "remind",

    "reminder",

    "alarm",

    "timer"

}


class BackgroundManager:

    def should_run_background(self, command):

        command = command.lower()

        print("BACKGROUND CHECK:", command)

        for task in BACKGROUND_TASKS:

            print("CHECKING:", task)

            words = command.split()

            if task in words:
                print("MATCH FOUND:", task)
                return True

        print("NO BACKGROUND MATCH")
        return False


background = BackgroundManager()