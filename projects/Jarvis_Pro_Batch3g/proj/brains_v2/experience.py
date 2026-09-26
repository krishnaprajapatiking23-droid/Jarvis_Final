class ExperienceEngine:

    def __init__(self):

        self.total_commands = 0

        self.total_open = 0

        self.total_chat = 0

        self.total_create = 0

    def learn(self, decision):

        self.total_commands += 1

        if decision == "OPEN":

            self.total_open += 1

        elif decision == "CHAT":

            self.total_chat += 1

        elif decision == "CREATE":

            self.total_create += 1

    def report(self):

        return {

            "commands": self.total_commands,

            "open": self.total_open,

            "chat": self.total_chat,

            "create": self.total_create

        }


experience = ExperienceEngine()