from brains_v3.runtime import runtime


class Brain:

    VERSION = "JarvisX V8"

    def process(self, command):

        runtime.start(command)

        return {
            "reply": "Brain V3 Started",
            "command": command
        }


brain = Brain()