"""
Automation Manager
"""

from automation.apps import open_app
from automation.browser import open_website
from automation.apps import close_app
from automation.folders import open_folder


class AutomationManager:

    def execute(self, command):

        result = open_app(command)
        if result:
            return result

        result = open_website(command)
        if result:
            return result

        result = open_folder(command)
        if result:
            return result

        return None


automation_manager = AutomationManager()