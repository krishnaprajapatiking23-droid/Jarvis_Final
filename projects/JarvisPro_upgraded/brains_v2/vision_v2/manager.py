from brains_v2.vision_v2.screenshot import capture
from brains_v2.vision_v2.ocr import read
from brains_v2.vision_v2.analyzer import analyze


def see():
    image = capture()
    text = read(image) if image else ""
    answer = analyze(text) if text else ""
    return {
        "image": image,
        "ocr": text,
        "analysis": answer,
    }


class VisionManager:
    """Vision manager used by core_bridge.handle_vision()."""

    def process(self, command=None):
        """Analyze the screen and return a description for the user."""
        result = see()
        ocr = result.get("ocr", "")
        analysis = result.get("analysis", "")

        if not ocr and not analysis:
            return "I couldn't read anything on the screen. Make sure a display and Tesseract OCR are available."

        if analysis:
            return analysis

        if ocr:
            return "On screen I can read:\n" + ocr

        return "I see the screen but couldn't analyze it."


vision_manager = VisionManager()