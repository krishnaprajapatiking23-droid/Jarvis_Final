from brains_v2.agents.base_agent import Agent

from automation.apps import open_app
from automation.browser import open_website
from automation.folders import open_folder
from automation.desktop import desktop
from automation.clipboard import clipboard
from automation.power import power
import automation.windows as windows


class AutomationAgent(Agent):

    name = "Automation Agent"

    description = "Controls Windows, applications, browser and desktop."

    priority = 100

    KEYWORDS = {

        "open",
        "launch",
        "run",
        "start",
        "close",
        "kill",
        "stop",
        "browser",
        "website",
        "google",
        "youtube",
        "desktop",
        "folder",
        "file",
        "minimize",
        "maximize",
        "clipboard",
        "copy",
        "paste",
        "shutdown",
        "restart",
        "sleep"

    }

    def can_handle(self, command):

        text = command.lower()

        return any(word in text for word in self.KEYWORDS)

    def score(self, command):

        text = command.lower()

        score = 0

        for word in self.KEYWORDS:

            if word in text:
                score += 10

        return min(score, 100)

    def plan(self, command):

        return [

            "Understand command",
            "Select automation module",
            "Execute",
            "Verify"

        ]

    def execute(self, command):

        text = command.lower()

        result = open_folder(command)
        if result:
            return self.success(result)

        result = open_app(command)
        if result:
            return self.success(result)

        if any(x in text for x in [
            "google",
            "youtube",
            "website",
            "browser"
        ]):

            result = open_website(command)

            return self.success(result)

        if "desktop" in text:

            return self.success(
                desktop.open_desktop()
            )

        if "clipboard" in text:

            return self.success(
                clipboard.execute(command)
            )

        if any(x in text for x in [
            "shutdown",
            "restart",
            "sleep"
        ]):

            return self.success(
                power.execute(command)
            )

        if "minimize" in text:

            return self.success(
                windows.minimize()
            )

        if "maximize" in text:

            return self.success(
                windows.maximize()
            )

        if "switch" in text:

            return self.success(
                windows.switch_window()
            )

        if "show desktop" in text:

            return self.success(
                windows.show_desktop()
            )

        if "close window" in text:

            return self.success(
                windows.close()
            )

        return {

            "success": False,

            "agent": self.name,

            "reply": "Automation command not recognised."

        }

    def success(self, result):

        return {

            "success": True,

            "agent": self.name,

            "plan": self.plan(""),

            "reply": result

        }

    def verify(self, result):

        return result.get("success", False)

    def learn(self, command, result):

        pass


agent = AutomationAgent()