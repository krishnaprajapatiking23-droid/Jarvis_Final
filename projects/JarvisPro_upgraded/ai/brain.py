"""
==========================================
JARVIS PRO
AI Brain V3
==========================================
"""

from compat.ollama_safe import ollama

from core.config import CHAT_MODEL
from core.logger import log

from conversation.prompt import build_prompt
from conversation.prompt import save_answer


def ask(question, username):

    messages = build_prompt(question, username)

    try:

        response = ollama.chat(

            model=CHAT_MODEL,

            messages=messages

        )

        answer = response["message"]["content"]

    except Exception as e:

        answer = f"Sorry {username}, I couldn't contact my AI brain.\n\n{e}"

    # Save conversation
    save_answer(answer)

    # Log
    log(f"User ({username}) : {question}")
    log(f"Jarvis : {answer}")

    return answer