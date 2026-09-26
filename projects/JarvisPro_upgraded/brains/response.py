import random
from conversation.manager import continue_conversation


RESPONSES = {

    "OPENED": [

        "I've opened Notepad. What are we working on?",

        "Done. Notepad is ready.",

        "Notepad is open. Let's build something amazing."

    ],

    "ALREADY_OPEN": [

        "Notepad is already open. Should I switch to it?",

        "I can already see Notepad running.",

        "Notepad is waiting for you."

    ],

    "FAILED": [

        "I couldn't open it.",

        "Something went wrong while opening it.",

        "It didn't open successfully."

    ]

}


def response(result):

    if isinstance(result, dict):

        status = result["status"]
        app = result["app"].capitalize()

    else:

        status = result
        app = ""

    text = random.choice(

        RESPONSES.get(

            status,

            ["Okay."]

        )

    )

    text = text.replace("Notepad", app)

    return continue_conversation(text)