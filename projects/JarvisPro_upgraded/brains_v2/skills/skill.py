class Skill:

    name = "Base Skill"

    description = ""

    def can_handle(self, command):

        return False

    def execute(self, command):

        return None