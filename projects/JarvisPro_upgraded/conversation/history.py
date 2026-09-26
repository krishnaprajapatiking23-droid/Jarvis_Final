history = []

MAX_HISTORY = 20


def add(role, content):

    history.append(
        {
            "role": role,
            "content": content
        }
    )

    if len(history) > MAX_HISTORY:
        history.pop(0)

def get_history():

    return history


def last_message():

    if not history:
        return None

    return history[-1]


def clear_history():

    history.clear()