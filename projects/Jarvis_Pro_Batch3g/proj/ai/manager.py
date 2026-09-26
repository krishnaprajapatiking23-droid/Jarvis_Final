from ai.router import detect_agent
from ai.agents import AGENTS

import ollama


def ask(command, messages):

    agent = detect_agent(command)

    model = AGENTS.get(agent)

    print("\n========== AI MANAGER ==========")
    print("Agent :", agent)
    print("Model :", model)
    print("================================\n")

    response = ollama.chat(

        model=model,

        messages=messages

    )

    return response["message"]["content"]