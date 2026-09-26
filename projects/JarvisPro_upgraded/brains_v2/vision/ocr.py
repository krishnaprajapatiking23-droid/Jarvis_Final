"""Canonical OCR engine (BUG 1).

The real implementation lives here; the legacy misspelled module is a thin
re-export wrapper. OCR degrades gracefully when pytesseract/Pillow are
unavailable (Phase 13).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

__all__ = [
    "OCRResult",
    "OCREngine",
    "engine",
    "image_to_string",
    "backend_status",
]

log = logging.getLogger(__name__)


@dataclass
class OCRResult:
    """Outcome of one OCR attempt."""

    ok: bool
    text: str = ""
    error: str = ""
    backend: str = ""

    def __bool__(self) -> bool:
        return self.ok


class OCREngine:
    """Thin wrapper around pytesseract with honest failure reporting."""

    def __init__(self) -> None:
        self._backend: Optional[Any] = None
        self._image: Optional[Any] = None
        self._loaded = False
        self._load_error = ""

    def _load_backend(self) -> bool:
        """Import the optional dependencies once, caching the outcome."""
        if self._loaded:
            return self._backend is not None
        self._loaded = True
        try:
            import pytesseract
            from PIL import Image
        except Exception as error:
            self._load_error = f"OCR backend unavailable: {type(error).__name__}"
            log.info(self._load_error)
            return False
        self._backend = pytesseract
        self._image = Image
        return True

    @property
    def available(self) -> bool:
        return self._load_backend()

    def backend_status(self) -> Dict[str, Any]:
        """Report what OCR can actually do right now."""
        return {
            "available": self._load_backend(),
            "error": self._load_error,
            "backend": "pytesseract" if self._backend else "",
        }

    def image_to_string(self, path: Any, language: str = "eng") -> OCRResult:
        """Extract text from an image file."""
        target = Path(str(path))
        if not target.is_file():
            return OCRResult(False, error=f"image not found: {target}")
        if not self._load_backend():
            return OCRResult(False, error=self._load_error)
        try:
            with self._image.open(target) as picture:  # type: ignore[union-attr]
                text = self._backend.image_to_string(  # type: ignore[union-attr]
                    picture, lang=language
                )
            return OCRResult(True, text=str(text).strip(), backend="pytesseract")
        except Exception as error:
            message = f"{type(error).__name__}: {error}"
            log.warning("ocr failed: %s", message)
            return OCRResult(False, error=message, backend="pytesseract")


engine = OCREngine()


def image_to_string(path: Any, language: str = "eng") -> OCRResult:
    """Module-level convenience wrapper around :data:`engine`."""
    return engine.image_to_string(path, language)


def backend_status() -> Dict[str, Any]:
    """Module-level convenience wrapper around :data:`engine`."""
    return engine.backend_status()
