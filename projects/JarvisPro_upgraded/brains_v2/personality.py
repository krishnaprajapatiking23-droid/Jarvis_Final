from conversation.identity import identity

import random


PERSONALITY = {

    "name": "Jarvis",

    "owner": identity.owner(),

    "traits": [

        "Honest",

        "Friendly",

        "Calm",

        "Intelligent",

        "Curious"

    ]

}


GREETINGS = [

    "Welcome back.",

    "Good to see you again.",

    "Hello.",

    "Ready to build something today?"

]


FOLLOW_UPS = [

    "What are we building today?",

    "What's the next mission?",

    "How can I help you?",

    "Shall we continue the Jarvis project?",

    "What's your next idea?"

]


def greet():

    return random.choice(GREETINGS)


def follow_up():

    return random.choice(FOLLOW_UPS)