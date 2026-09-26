WORDS = {

    "it",

    "that",

    "this",

    "there",

    "again"

}


def has_reference(command):

    command = command.lower()

    return any(word in command for word in WORDS)