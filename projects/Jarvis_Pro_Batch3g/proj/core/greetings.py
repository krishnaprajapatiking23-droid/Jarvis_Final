from datetime import datetime


def get_greeting(name):

    hour = datetime.now().hour

    if hour < 12:
        greeting = "Good Morning"

    elif hour < 17:
        greeting = "Good Afternoon"

    elif hour < 21:
        greeting = "Good Evening"

    else:
        greeting = "Hello"

    return f"{greeting}, {name}!"