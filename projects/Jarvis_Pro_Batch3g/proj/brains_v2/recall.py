class RecallEngine:

    def __init__(self):

        self.last_command = ""

        self.last_reply = ""

    def update(self, command, reply):

        self.last_command = command

        self.last_reply = reply

    def command(self):

        return self.last_command

    def reply(self):

        return self.last_reply

    def data(self):

        return {

            "last_command": self.last_command,

            "last_reply": self.last_reply

        }


recall = RecallEngine()