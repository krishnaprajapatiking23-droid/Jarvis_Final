from coding.ai import ask_coding


def debug_code(error):

    prompt = f"""
Debug this error.

Error:

{error}

Return:

1. Cause
2. Solution
3. Correct Code
4. Explanation
"""

    return ask_coding(prompt)