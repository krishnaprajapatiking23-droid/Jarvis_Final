from core.intent import detect_intent

from automation.apps import open_app
from automation.browser import open_website
from automation.folders import open_folder
from automation.file_manager import create_folder

from thinking.planner import plan
from context.manager import get_context
from brains.decision import decide
from brains.response import response


class Brain:

    def process(self, command):

        thinking = plan(command)

        context = get_context()

        action = decide(
            thinking,
            context
        )

        automation = self.automation(command)


        if automation:

            print("Automation Result:", automation)

            text = response(automation)

            print("Brain Response:", text)

            return {

                "thinking": thinking,

                "context": context,

                "action": automation,

                "response": text

            }
        
        text = response(action)

        return {

            "thinking": thinking,

            "context": context,

            "action": action,

            "response": text

        }

    def automation(self, command):

        print("\n===== BRAIN AUTOMATION =====")
        print("Command:", command)

        intent = detect_intent(command)

        print("Intent:", intent)

        if intent == "open":

            print("Trying open_folder...")
            result = open_folder(command)
            print("Folder Result:", result)

            if result:
                return result

            print("Trying open_app...")
            result = open_app(command)
            print("App Result:", result)

            if result:
                return result

            print("Trying open_website...")
            result = open_website(command)
            print("Website Result:", result)

            if result:
                return result

        print("Automation returned None")

        return None


brain = Brain()


def brain_manager(command, username):

    result = brain.process(command)

    return result["response"]


def think(command):

    result = brain.process(command)

    return result