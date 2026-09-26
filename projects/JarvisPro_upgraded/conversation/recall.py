from conversation.manager import get_history


def last_message():

    data = get_history()

    if not data:

        return None

    return data[-1]