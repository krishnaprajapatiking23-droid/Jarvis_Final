def think(command, context):

    command = command.lower()

    if "open notepad" in command:

        if context.get("notepad"):

            return "NOTEPAD_ALREADY_OPEN"

        return "OPEN_NOTEPAD"

    if "open chrome" in command:

        if context.get("chrome"):

            return "CHROME_ALREADY_OPEN"

        return "OPEN_CHROME"

    return "UNKNOWN"