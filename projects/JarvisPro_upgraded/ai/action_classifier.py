from compat.ollama_safe import ollama

from core.config import CHAT_MODEL


SYSTEM = """
You are Jarvis's command classifier.

Your job is ONLY to classify the user's request.

Return EXACTLY ONE of these words.

OPEN_NOTEPAD
OPEN_CALCULATOR
OPEN_PAINT
OPEN_CMD
OPEN_EXPLORER
CHAT

Examples

User: Open notepad
Answer: OPEN_NOTEPAD

User: I need somewhere to write my ideas.
Answer: OPEN_NOTEPAD

User: I want to write a letter.
Answer: OPEN_NOTEPAD

User: I need a text editor.
Answer: OPEN_NOTEPAD

User: I want to calculate numbers.
Answer: OPEN_CALCULATOR

User: I need to do maths.
Answer: OPEN_CALCULATOR

User: I want to draw.
Answer: OPEN_PAINT

User: Open terminal.
Answer: OPEN_CMD

User: Show me a joke.
Answer: CHAT

Never explain.

Never answer the user.

Return ONE WORD ONLY.
"""


def classify(command):

    response = ollama.chat(
        model=CHAT_MODEL,
        messages=[
            {
                "role": "system",
                "content": SYSTEM
            },
            {
                "role": "user",
                "content": command
            }
        ]
    )

    answer = response["message"]["content"]

    answer = answer.strip().upper()

    print("\n===== AI CLASSIFIER =====")
    print("Command :", command)
    print("Intent  :", answer)
    print("=========================\n")

    return answer