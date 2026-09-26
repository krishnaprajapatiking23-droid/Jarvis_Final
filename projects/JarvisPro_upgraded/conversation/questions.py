import random

QUESTIONS = [

    "Would you like me to explain it?",

    "Should I continue?",

    "Do you want another way?",

    "Would you like more details?",

    "Can I help with anything else?"

]

def ask():

    return random.choice(QUESTIONS)