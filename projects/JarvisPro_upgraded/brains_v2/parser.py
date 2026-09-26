"""
Command Parser V1
"""

ACTIONS = [
    "open",
    "close",
    "search",
    "play",
    "create",
    "delete",
    "rename",
    "remember",
    "forget",
    "find"
]


class CommandParser:

    def parse(self, command):

        text = command.lower().strip()

        action = None

        for word in ACTIONS:
            if text.startswith(word):
                action = word
                break

        # Default action for known apps/websites
        if action is None:

            known_targets = [
               "notepad",
                "calculator",
                "calc",
                "paint",
                "cmd",
                "terminal",
                "explorer",
                "youtube",
                "google",
                "chrome"
            ]

            if text in known_targets:
               action = "open"

        if action:
            target = text[len(action):].strip() if text.startswith(action) else text
        else:
            target = text

        return {
            "action": action,
            "target": target,
            "original": command
        }


parser = CommandParser()