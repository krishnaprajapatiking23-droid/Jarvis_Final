from business.ai import ask_business


def find_audience(command):

    prompt = f"""
You are a Meta Ads targeting expert.

{command}

Give:

1. Age
2. Gender
3. Interests
4. Behaviors
5. Cities
6. Pain Points
7. Buying Intent
"""

    return ask_business(prompt)