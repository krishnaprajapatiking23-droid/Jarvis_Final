UNSATISFIED = [

    "not satisfied",
    "try again",
    "wrong",
    "bad answer",
    "better answer",
    "not good",
    "incorrect",
    "this is wrong",
    "i expected more",
    "doesn't help"

]


def is_unsatisfied(text):

    text = text.lower()

    for phrase in UNSATISFIED:

        if phrase in text:
            return True

    return False


def clarification_questions():

    return [

        "What exactly do you want to achieve?",

        "Would you like a beginner or advanced explanation?",

        "Do you want examples?",

        "Should I answer step by step?",

        "Is there anything specific that was missing from my previous answer?"

    ]