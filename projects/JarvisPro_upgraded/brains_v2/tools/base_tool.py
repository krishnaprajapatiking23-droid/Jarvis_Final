class Tool:

    name = "Base Tool"

    description = ""

    def can_handle(self, command):

        return False

    def execute(self, command):

        return None