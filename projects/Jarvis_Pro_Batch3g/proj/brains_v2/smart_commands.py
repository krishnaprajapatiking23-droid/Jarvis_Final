COMMANDS = {
    "not bad": "notepad",
    "note bad": "notepad",
    "node pad": "notepad",
    "chrome browser": "chrome",
    "google chrome": "chrome",
    "calc": "calculator",
    "command prompt": "cmd",
    "file explorer": "explorer",
}


def fix(command):

    text = command.lower().strip()

    # Exact command replacement only
    if text in COMMANDS:
        return COMMANDS[text]

    # Replace whole phrases only
    for old, new in COMMANDS.items():

        if f" {old} " in f" {text} ":
            text = f" {text} ".replace(f" {old} ", f" {new} ").strip()

    return text