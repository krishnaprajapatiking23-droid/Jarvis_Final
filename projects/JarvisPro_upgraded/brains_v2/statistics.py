class Statistics:

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

    def report(self):

        if self.total_commands == 0:

            accuracy = 0

        else:

            accuracy = round(
                self.success * 100 / self.total_commands,
                2
            )

        return {

            "commands": self.total_commands,

            "success": self.success,

            "failed": self.failed,

            "accuracy": accuracy

        }


statistics = Statistics()