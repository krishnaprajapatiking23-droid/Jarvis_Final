from compat.ollama_safe import ollama

from core.config import CHAT_MODEL

from ai.conversation import add, get

def ask_business(prompt):

    add("user", prompt)

    response = ollama.chat(

        model=CHAT_MODEL,

        messages=get(),

        think=False

    )

    answer = response["message"]["content"]

    add("assistant", answer)

    return answer