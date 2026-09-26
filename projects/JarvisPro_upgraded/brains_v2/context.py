from conversation.identity import identity

class BrainContext:

    def __init__(self):

        self.user = identity.owner()

        self.command = ""

        self.decision = ""

        self.last_command = ""

        self.last_reply = ""

        self.last_app = ""

        self.current_task = ""

        self.current_project = "Jarvis Pro"

    def update(self, command, decision):

        self.last_command = self.command

        self.command = command

        self.decision = decision

        # Application state is not conversation topic: the active
        # app only changes when the user asked for an action, so
        # "Tell me about Notepad." leaves the app state alone.
        try:
            from conversation.request_type import is_action_request

            wants_action = is_action_request(command)

        except Exception:  # pragma: no cover - defensive
            wants_action = True

        if not wants_action:
            return

        if "notepad" in command.lower():

            self.last_app = "Notepad"

        elif "calculator" in command.lower():

            self.last_app = "Calculator"

        elif "paint" in command.lower():

            self.last_app = "Paint"


context = BrainContext()