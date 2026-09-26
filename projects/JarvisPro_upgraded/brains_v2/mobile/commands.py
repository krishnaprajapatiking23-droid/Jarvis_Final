"""
Jarvis Mobile Commands
"""

from brains_v2.manager import brain


class CommandManager:

    def execute(self, command):

        print()

        print("=" * 60)

        print("Incoming Mobile Command")

        print(command)

        print("=" * 60)

        result = brain.process(command)

        return result


commands = CommandManager()