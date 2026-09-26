import random

GREETINGS = [

    "Hey Krishna! 😊",

    "Welcome back Krishna.",

    "Good to see you again!",

    "Hello Krishna, what's today's mission?",

    "Hi Krishna! Ready to build something amazing?"

]


def random_greeting():

    return random.choice(GREETINGS)