class Runtime:

    def __init__(self):

        self.total_commands = 0
        self.success = 0
        self.failed = 0

        self.last_command = ""
        self.last_intent = ""
        self.last_plan = ""
        self.last_result = ""
        self.last_reply = ""

        self.is_running = False

    def start(self, command):

        self.is_running = True
        self.total_commands += 1
        self.last_command = command

    def command_success(self):

        self.success += 1

    def command_failed(self):

        self.failed += 1

    def stop(self):

        self.is_running = False


runtime = Runtime()