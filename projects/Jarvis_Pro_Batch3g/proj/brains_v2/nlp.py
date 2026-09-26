import random


HELLO = [

    "Hello.",

    "Hey there.",

    "Welcome back.",

    "Good to see you again.",

    "Hi."

]

HOW_ARE_YOU = [

    "I'm doing well. How are you?",

    "Everything is running smoothly.",

    "Ready for today's mission.",

    "Doing great. What shall we build today?"

]

THANKS = [

    "You're welcome.",

    "Always happy to help.",

    "My pleasure.",

    "Anytime."

]


def chat(command):

    text = command.lower()

    if any(x in text for x in ["hello", "hi", "hey"]):

        return random.choice(HELLO)

    if "how are you" in text:

        return random.choice(HOW_ARE_YOU)

    if any(x in text for x in ["thank", "thanks"]):

        return random.choice(THANKS)

    return None