from brains_v2.llm.manager import ask


def analyze(image_path):

    prompt = f"""

You are Jarvis.

The user captured a screenshot.

Image file:

{image_path}

Explain:

1. What is probably visible.
2. What the user might be doing.
3. Any obvious errors.
4. Suggestions.

"""

    return ask(prompt)