from thinking.reason import analyze


def plan(command):

    intent = analyze(command)

    return {
        "command": command,
        "intent": intent
    }