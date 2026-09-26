OPEN = [
    "open",
    "launch",
    "start",
    "run",
    "use"
]

SHOW = [
    "show",
    "display",
    "list",
    "read"
]

CREATE = [
    "create",
    "make",
    "build"
]


def classify(command):

    text = command.lower()

    if any(word in text for word in OPEN):
        return "OPEN"

    if any(word in text for word in SHOW):
        return "SHOW"

    if any(word in text for word in CREATE):
        return "CREATE"

    return "CHAT"