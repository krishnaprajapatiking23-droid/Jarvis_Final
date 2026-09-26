import random

FOLLOW_UP = [

    "What are we working on?",

    "How can I help?",

    "What's the next goal?",

    "Let's continue where we stopped.",

    "Tell me your plan."

]


def follow_up():

    return random.choice(FOLLOW_UP)