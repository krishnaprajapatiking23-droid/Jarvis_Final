class Reflection:

    def __init__(self):

        self.total_commands = 0
        self.success = 0
        self.failed = 0

    def update(self, verification):

        self.total_commands += 1

        if verification["success"]:

            self.success += 1

        else:

            self.failed += 1

    def accuracy(self):

        if self.total_commands == 0:

            return 0

        return round(
            self.success * 100 / self.total_commands,
            2
        )

    def report(self):

        return {

            "commands": self.total_commands,

            "success": self.success,

            "failed": self.failed,

            "accuracy": self.accuracy()

        }


reflection = Reflection()