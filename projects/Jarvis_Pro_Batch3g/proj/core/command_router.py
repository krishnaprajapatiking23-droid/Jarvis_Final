import ollama

from core.config import AI_MODEL


SYSTEM_PROMPT = """
You are an AI command classifier.

Return ONLY ONE WORD.

Possible outputs are:

OPEN_APP
OPEN_FOLDER
CREATE_FOLDER
MEMORY
REMINDER
SEARCH
CHAT

Nothing else.
"""


def classify(command):

    response = ollama.chat(
        model=AI_MODEL,
        messages=[
            {
                "role": "system",
                "content": SYSTEM_PROMPT
            },
            {
                "role": "user",
                "content": command
            }
        ]
    )

    return response["message"]["content"].strip().upper()