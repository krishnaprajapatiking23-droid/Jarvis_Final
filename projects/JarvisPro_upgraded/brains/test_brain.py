from brains.classifier import classify_brain

from agents.manager import run_agent

from ai.brain import ask


def route_brain(command, username):

    brain = classify_brain(command)

    print("\n========== AI ==========")
    print("Selected Brain :", brain)
    print("========================\n")

    if brain == "business":
        return run_agent("business", command)

    elif brain == "coding":
        return run_agent("coding", command)

    elif brain == "vision":
        return "Vision Agent is under development."

    else:
        return ask(command, username)