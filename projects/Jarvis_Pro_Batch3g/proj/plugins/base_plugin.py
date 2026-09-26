class BasePlugin:

    name = "Plugin"

    def can_handle(self, command):
        return False

    def execute(self, command):
        return None