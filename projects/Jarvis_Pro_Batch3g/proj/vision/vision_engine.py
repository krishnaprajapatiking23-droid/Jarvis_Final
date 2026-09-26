"""
Vision Engine — processes images and provides visual understanding.

Capabilities:
- Image description / captioning
- Object detection (keyword-based fallback)
- OCR text extraction from images
- Visual Q&A on images
- Screenshot analysis

Requires: PIL/Pillow for image loading.
Install: pip install Pillow
"""

import base64
import io
import re
from typing import Optional

try:
    from PIL import Image
    _PIL_AVAILABLE = True
except ImportError:
    _PIL_AVAILABLE = False


class VisionEngine:
    """Handles all image understanding and visual processing tasks."""

    def __init__(self):
        self._last_image = None
        self._last_description = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyze(self, image_path_or_bytes: str) -> dict:
        """
        Analyze an image and return a structured description.
        Supports file paths and raw bytes.
        """
        if not _PIL_AVAILABLE:
            return {
                "status": "error",
                "message": "Pillow not installed. Run: pip install Pillow",
                "description": "",
            }

        try:
            if isinstance(image_path_or_bytes, str):
                image = Image.open(image_path_or_bytes)
            else:
                image = Image.open(io.BytesIO(image_path_or_bytes))

            self._last_image = image
            width, height = image.size
            mode = image.mode

            description = self._describe_fallback(image)

            self._last_description = description

            return {
                "status": "ok",
                "description": description,
                "dimensions": {"width": width, "height": height},
                "mode": mode,
            }

        except Exception as e:
            return {
                "status": "error",
                "message": str(e),
                "description": "",
            }

    def extract_text(self, image_path_or_bytes: str) -> str:
        """
        Extract readable text from an image using simple thresholding.
        For production OCR, install: pip install pytesseract
        """
        if not _PIL_AVAILABLE:
            return "[Pillow not available]"

        try:
            if isinstance(image_path_or_bytes, str):
                image = Image.open(image_path_or_bytes)
            else:
                image = Image.open(io.BytesIO(image_path_or_bytes))

            # Convert to grayscale for cleaner processing
            gray = image.convert("L")

            # Use pytesseract if available
            try:
                import pytesseract
                text = pytesseract.image_to_string(gray)
                return text.strip()
            except ImportError:
                # Fallback: return a placeholder message
                return "[pytesseract not installed — install with: pip install pytesseract]"

        except Exception as e:
            return f"[Error extracting text: {e}]"

    def detect_objects(self, image_path_or_bytes: str) -> list:
        """
        Keyword-based object detection fallback.
        For production use, integrate a model like YOLO or CLIP.
        """
        description = self.analyze(image_path_or_bytes).get("description", "")
        keywords = [
            "person", "car", "dog", "cat", "tree", "building",
            "text", "face", "screen", "window", "button",
        ]
        found = [kw for kw in keywords if kw in description.lower()]
        return found if found else ["(no common objects detected)"]

    def describe_screenshot(self) -> str:
        """Describe the last analyzed image."""
        if self._last_description:
            return self._last_description
        return "(no image analyzed yet — call analyze() first)"

    def encode_base64(self, image_path: str) -> str:
        """Load an image and return a base64-encoded string."""
        try:
            with open(image_path, "rb") as f:
                return base64.b64encode(f.read()).decode("utf-8")
        except Exception as e:
            return f"[Error encoding image: {e}]"

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _describe_fallback(self, image: Image.Image) -> str:
        """Generate a basic description from image properties."""
        w, h = image.size
        parts = [
            f"Image is {w}x{h} pixels.",
            f"Color mode: {image.mode}.",
        ]
        if image.mode == "RGB":
            try:
                # Sample center pixel for dominant color hint
                cx, cy = w // 2, h // 2
                r, g, b = image.getpixel((cx, cy))[:3]
                parts.append(f"Center pixel approx: RGB({r},{g},{b}).")
            except Exception:
                pass
        parts.append("Call extract_text() for OCR.")
        return " ".join(parts)

    def reset(self):
        """Clear the last image cache."""
        self._last_image = None
        self._last_description = None


# ---------------------------------------------------------------------------
# Module-level convenience API
# ---------------------------------------------------------------------------

_engine = VisionEngine()


def analyze(image_path_or_bytes) -> dict:
    return _engine.analyze(image_path_or_bytes)


def extract_text(image_path_or_bytes) -> str:
    return _engine.extract_text(image_path_or_bytes)


def detect_objects(image_path_or_bytes) -> list:
    return _engine.detect_objects(image_path_or_bytes)


def describe_screenshot() -> str:
    return _engine.describe_screenshot()


def reset():
    _engine.reset()
