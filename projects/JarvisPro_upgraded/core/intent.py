def detect_intent(command):

    command = command.lower()

    if any(word in command for word in [
        "create folder",
        "make folder",
        "new folder",
        "create a folder",
        "make a folder",
        "folder called",
        "folder named"
    ]):
        return "create_folder"

    if any(word in command for word in [
        "open",
        "launch",
        "start",
        "run"
    ]):
        return "open"

    if any(word in command for word in [
        "remember",
        "save this"
    ]):
        return "memory"

    return "ai"