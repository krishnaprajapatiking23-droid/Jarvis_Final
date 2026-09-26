from personality.greetings import random_greeting
from personality.style import follow_up


def build_response(answer):

    return f"{answer}\n\n{follow_up()}"


def greet():

    return f"{random_greeting()}\n\n{follow_up()}"