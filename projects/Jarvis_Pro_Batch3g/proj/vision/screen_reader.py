from vision.screenshot import take_screenshot
from vision.ocr import read_text

from ai.brain import ask


def analyze_screen(username):

    image = take_screenshot()

    text = read_text(image)

    if not text:

        return "I couldn't find any readable text on the screen."

    prompt = f"""
The following text was extracted from the user's screen.

{text}

Explain what the user is currently doing in a short and helpful way.
"""

    return ask(prompt, username)