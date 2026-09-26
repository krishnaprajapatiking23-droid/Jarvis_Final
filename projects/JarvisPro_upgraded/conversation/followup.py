import random

FOLLOW_UP = [

    "What are we building today?",

    "What's our next mission?",

    "How can I help you now?",

    "Let's continue the project.",

    "Ready for the next step?",

    "What's the next challenge?"

]

def follow():

    return random.choice(FOLLOW_UP)