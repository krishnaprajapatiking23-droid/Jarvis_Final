import json


def load_profile():

    with open(
        "memory/user_profile.json",
        encoding="utf-8"
    ) as f:

        return json.load(f)


def load_preferences():

    with open(
        "memory/preferences.json",
        encoding="utf-8"
    ) as f:

        return json.load(f)
    
from memory.session import SESSION


def remember(command, response):

    SESSION["last_command"] = command

    SESSION["last_response"] = response

    SESSION["conversation"].append(

        {
            "user": command,
            "jarvis": response
        }

    )

def last():

    if SESSION["conversation"]:

        return SESSION["conversation"][-1]

    return None