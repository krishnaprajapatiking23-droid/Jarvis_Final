from business.ai import ask_business


def classify_request(command):

    prompt = f"""
You are Jarvis's routing engine.

Your job is to classify a request.

Return ONLY ONE WORD.

Possible answers:

automation
business
coding
vision
study
mission
chat

Do NOT explain.
Do NOT think.
Do NOT add punctuation.
Do NOT write sentences.

Request:

{command}
"""

    answer = ask_business(prompt)

    answer = answer.strip().lower()

    categories = [
        "automation",
        "business",
        "coding",
        "vision",
        "study",
        "mission",
        "chat"
    ]

    for category in categories:
        if category in answer:
            return category

    return "chat"