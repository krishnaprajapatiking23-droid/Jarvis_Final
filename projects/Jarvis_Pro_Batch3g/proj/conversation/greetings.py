"""
Jarvis Greetings
"""

import random

GREETINGS = [

    "Hello.",

    "Namaste.",

    "Welcome back.",

    "Good to see you again.",

    "Yes?",

    "I'm listening.",

    "How can I help you today?",

    "Always ready.",

    "Good to have you back."

]

GOODBYE = [

    "I'll be here whenever you need me.",

    "Going back to standby mode.",

    "Conversation ended.",

    "Take care.",

    "Talk to you soon.",

    "Returning to standby."

]


def greeting():

    return random.choice(GREETINGS)


def goodbye():

    return random.choice(GOODBYE)