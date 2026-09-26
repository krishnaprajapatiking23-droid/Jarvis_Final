class HabitEngine:

    def __init__(self):

        self.apps = {}

        self.commands = {}

    def learn(self, command):

        command = command.lower()

        self.commands[command] = self.commands.get(command, 0) + 1

        words = {

            "notepad": "Notepad",

            "calculator": "Calculator",

            "paint": "Paint",

            "chrome": "Chrome",

            "explorer": "Explorer"

        }

        for key, value in words.items():

            if key in command:

                self.apps[value] = self.apps.get(value, 0) + 1

    def favorite_app(self):

        if not self.apps:

            return None

        return max(self.apps, key=self.apps.get)

    def favorite_command(self):

        if not self.commands:

            return None

        return max(self.commands, key=self.commands.get)


habits = HabitEngine()