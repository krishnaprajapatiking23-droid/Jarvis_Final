class LearningEngine:

    def __init__(self):

        self.apps = {}

        self.commands = {}

    def learn(self, command):

        command = command.lower()

        self.commands[command] = self.commands.get(command, 0) + 1

        if "notepad" in command:

            self.apps["notepad"] = self.apps.get("notepad", 0) + 1

        elif "calculator" in command:

            self.apps["calculator"] = self.apps.get("calculator", 0) + 1

        elif "paint" in command:

            self.apps["paint"] = self.apps.get("paint", 0) + 1

    def favourite_app(self):

        if not self.apps:

            return None

        return max(self.apps, key=self.apps.get)

    def favourite_command(self):

        if not self.commands:

            return None

        return max(self.commands, key=self.commands.get)


learning = LearningEngine()