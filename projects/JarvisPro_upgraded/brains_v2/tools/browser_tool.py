from brains_v2.tools.base_tool import Tool

from automation.browser import open_website


class BrowserTool(Tool):

    name = "Browser Tool"

    description = "Open websites."

    def can_handle(self, command):

        return "http" in command.lower() or "www" in command.lower()

    def execute(self, command):

        return open_website(command)