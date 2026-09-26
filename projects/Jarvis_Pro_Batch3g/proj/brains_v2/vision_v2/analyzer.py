from brains_v2.llm.manager import ask


def analyze(text):

    prompt = f"""

You are Jarvis.

The following text was extracted from the user's screen.

{text}

Explain what is happening.
Mention any error.
Suggest what the user should do next.

"""

    return ask(prompt)