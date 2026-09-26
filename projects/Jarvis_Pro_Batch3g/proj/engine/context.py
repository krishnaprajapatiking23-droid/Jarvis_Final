context = {
    "user": None,
    "project": None,
    "workspace": None,
    "goal": None
}


def set_context(key, value):

    context[key] = value


def get_context():

    return context