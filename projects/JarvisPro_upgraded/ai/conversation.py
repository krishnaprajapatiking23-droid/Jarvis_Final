history = []


def add(role, message):

    history.append({
        "role": role,
        "content": message
    })

    if len(history) > 10:
        history.pop(0)


def get():

    return history


def clear():

    history.clear()