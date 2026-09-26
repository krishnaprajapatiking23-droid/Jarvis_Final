from brains_v2.tools.base_tool import Tool

from automation.apps import open_app


class AppTool(Tool):

    name = "Application Tool"

    description = "Open desktop applications."

    def can_handle(self, command):

        command = command.lower()

        return any(word in command for word in [

            "open",

            "launch",

            "run"

        ])

    def execute(self, command):

        return open_app(command)