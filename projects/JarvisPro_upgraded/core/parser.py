OPEN_WORDS = [
    "open",
    "launch",
    "start",
    "run",
    "use"
]


def detect_open(command):

    command = command.lower()

    return any(word in command for word in OPEN_WORDS)