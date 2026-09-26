from coding.ai import ask_coding


def explain_code(code):

    prompt = f"""
Explain this code line by line.

Code:

{code}
"""

    return ask_coding(prompt)