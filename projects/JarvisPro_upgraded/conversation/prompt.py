from conversation.personality import get_personality
from conversation.history import history, add


def build_prompt(user_message, username):

    add("user", user_message)

    system_prompt = {
        "role": "system",
        "content": get_personality(username)
    }

    messages = [system_prompt]

    messages.extend(history)

    return messages


def save_answer(answer):

    add("assistant", answer)