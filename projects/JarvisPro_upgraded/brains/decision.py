def decide(plan, context):

    intent = plan["intent"]

    command = plan["command"].lower()

    if intent == "OPEN_APP":

        if "notepad" in command:

            if context["notepad"]:

                return "NOTEPAD_ALREADY_OPEN"

            return "OPEN_NOTEPAD"

        if "chrome" in command:

            if context["chrome"]:

                return "CHROME_ALREADY_OPEN"

            return "OPEN_CHROME"

    return "DEFAULT"