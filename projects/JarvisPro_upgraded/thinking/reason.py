def analyze(command: str):

    command = command.lower().strip()

    if "open" in command:
        return "OPEN_APP"

    if "close" in command:
        return "CLOSE_APP"

    if "search" in command:
        return "SEARCH"

    if "remember" in command:
        return "MEMORY"

    return "CHAT"