from vision.screenshot import take_screenshot
from vision.ocr import read_text, OCRResult

from ai.brain import ask


def read_screen():
    """Take a screenshot and return extracted text, or '' on any failure.
    
    This is the canonical screen-reading entry point used by core_bridge.
    Does NOT raise -- callers handle empty text gracefully.
    """
    path = take_screenshot()
    if not path:
        return ""
    try:
        result = read_text(path)
        return result if result else ""
    except Exception:
        return ""


def analyze_screen(username):
    """Describe what the user is currently doing based on the screen."""
    path = take_screenshot()

    if not path:
        return "I couldn't take a screenshot. Make sure a display is available."

    try:
        text = read_text(path)
    except RuntimeError:
        return "I couldn't read the screen. Check that Tesseract OCR is installed."

    if not text:
        return "I couldn't find any readable text on the screen."

    prompt = f"""
The following text was extracted from the user's screen.

{text}

Explain what the user is currently doing in a short and helpful way.
"""

    try:
        return ask(prompt, username)
    except Exception:
        return "I can see text on screen but couldn't analyze it. The AI brain may be unavailable."
