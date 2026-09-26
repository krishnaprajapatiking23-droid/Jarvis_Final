class BrainState:

    def __init__(self):

        self.running = False

        self.total_commands = 0

        self.total_success = 0

        self.total_failed = 0

    def command(self):

        self.total_commands += 1

    def success(self):

        self.total_success += 1

    def failed(self):

        self.total_failed += 1

    def status(self):

        return {

            "running": self.running,

            "commands": self.total_commands,

            "success": self.total_success,

            "failed": self.total_failed

        }


brain_state = BrainState()