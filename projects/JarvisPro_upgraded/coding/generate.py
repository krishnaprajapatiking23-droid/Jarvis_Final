from coding.ai import ask_coding


def generate_code(request):

    prompt = f"""
Write Python code.

Task:

{request}

Generate clean, well-commented code.
"""

    return ask_coding(prompt)