"""
==========================================
JARVIS PRO
Vision perception
==========================================

Roadmap sections 7 (full screen understanding), 8 (screenshot analysis),
9 (OCR), 13 (UI understanding), 14 (button/text understanding) and
15 (element identification).

Two stages turn pixels into structure.

:class:`OCRProvider` wraps tesseract's ``image_to_data``, which returns a word
per row with a box and a confidence - so OCR here produces *located* text, not
a wall of characters. It also preprocesses light-on-dark regions, because
white button labels on a coloured fill are the single most common thing
tesseract gets wrong on a UI screenshot; without inversion "Login" reads as
"gin".

:class:`ElementDetector` finds widgets from the pixels themselves, by locating
closed rectangular contours. It is genuinely independent of OCR: it will find
an unlabelled icon that carries no text at all. Classification then combines
the two - a filled rectangle *containing* centred text is a button, an empty
outlined rectangle with a label above it is an input.

What this is not: it is not a vision model, and nothing here claims to
understand an arbitrary photograph. Section 62 forbids calling OCR "full
visual understanding", so the pipeline reports ``degraded`` whenever the
vision model is absent.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any

from .providers import (
    INVALID_INPUT,
    Provider,
    VisionResult,
)
from .types import (
    BBox,
    Element,
    merge_boxes,
    suppress_overlaps,
)

# Tesseract reports -1 for non-text rows; anything under this is noise.
MIN_WORD_CONFIDENCE = 30.0

# Words closer than this on the same line belong to the same phrase.
WORD_GAP = 26

# A contour smaller than this is texture, not a widget. Kept low enough to
# admit a checkbox (a 24px square is 576) - at 900 every checkbox on every
# screen was silently dropped. The extent and side-length filters below carry
# the noise rejection instead.
MIN_ELEMENT_AREA = 320
MIN_ELEMENT_SIDE = 14

# Text that names an action rather than describing a thing (section 14).
ACTION_WORDS = {
    "ok", "cancel", "submit", "send", "save", "delete", "remove", "login",
    "log in", "sign in", "sign up", "register", "continue", "next", "back",
    "close", "confirm", "apply", "search", "upload", "download", "add",
    "edit", "update", "retry", "refresh", "start", "stop", "pause", "play",
    "yes", "no", "accept", "decline", "allow", "deny", "keep", "discard",
    "buy", "purchase", "checkout", "pay", "finish", "done", "open",
}

# Actions whose effect is hard or impossible to undo (section 19).
DESTRUCTIVE_WORDS = {
    "delete", "remove", "erase", "discard", "destroy", "wipe", "purge",
    "uninstall", "reset", "revoke", "deactivate", "close account",
    "buy", "purchase", "checkout", "pay", "send", "submit order", "confirm order",
}

# Labels that usually sit beside an input rather than name an action.
FIELD_WORDS = {
    "username", "user name", "email", "e-mail", "password", "search",
    "name", "address", "phone", "city", "country", "postcode", "zip",
    "message", "subject", "title", "description", "category", "comment",
}


@dataclass
class TextSpan:
    """One located run of text."""

    text: str
    bbox: BBox
    confidence: float
    line: int = 0
    block: int = 0

    def report(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "bbox": self.bbox.report(),
            "confidence": round(float(self.confidence), 4),
            "line": self.line,
            "block": self.block,
        }


class OCRProvider(Provider):
    """Tesseract with word boxes, confidence and light-on-dark handling."""

    name = "tesseract"
    capability = "OCR"
    requires = ("pytesseract", "PIL")

    def _probe(self) -> tuple[bool, str, dict[str, Any]]:
        ok, reason, detail = super()._probe()

        if not ok:
            return ok, reason, detail

        # The python package importing does not mean the tesseract binary is
        # installed; that is the usual failure and it must be distinguished.
        try:
            import pytesseract

            version = str(pytesseract.get_tesseract_version())

            return True, "", {"engine": f"tesseract {version}"}

        except Exception as exc:
            return False, (
                f"pytesseract is installed but the tesseract binary is not "
                f"usable: {type(exc).__name__}"
            ), {}

    # ------------------------------------------------------------- reading

    def read(
        self,
        image: Any,
        language: str = "eng",
        region: BBox | None = None,
        invert: bool = False,
        min_confidence: float = MIN_WORD_CONFIDENCE,
    ) -> VisionResult:
        """Read located text. Returns a list of :class:`TextSpan`."""

        if image is None:
            return VisionResult.fail(
                INVALID_INPUT, "no image supplied", provider=self.name,
                recoverable=False,
            )

        def run():
            import pytesseract
            from PIL import Image, ImageOps

            picture = image

            if isinstance(picture, (str, bytes)):
                picture = Image.open(picture)

            picture = picture.convert("RGB")
            offset = (0, 0)

            if region is not None:
                picture = picture.crop(
                    (region.x, region.y, region.right, region.bottom)
                )
                offset = (region.x, region.y)

            prepared = ImageOps.grayscale(picture)

            if invert:
                prepared = ImageOps.invert(prepared)

            data = pytesseract.image_to_data(
                prepared, lang=language, output_type=pytesseract.Output.DICT
            )

            spans: list[TextSpan] = []

            for index in range(len(data.get("text", []))):
                word = str(data["text"][index]).strip()

                if not word:
                    continue

                try:
                    confidence = float(data["conf"][index])

                except (TypeError, ValueError):
                    confidence = -1.0

                if confidence < min_confidence:
                    continue

                spans.append(
                    TextSpan(
                        text=word,
                        bbox=BBox(
                            int(data["left"][index]) + offset[0],
                            int(data["top"][index]) + offset[1],
                            int(data["width"][index]),
                            int(data["height"][index]),
                        ),
                        confidence=round(confidence / 100.0, 4),
                        line=int(data.get("line_num", [0])[index]),
                        block=int(data.get("block_num", [0])[index]),
                    )
                )

            return spans

        return self.guard(run, timeout=30.0)

    def read_text(self, image: Any, language: str = "eng") -> VisionResult:
        """Plain text, for callers that do not need geometry."""

        result = self.read(image, language)

        if not result.success:
            return result

        return VisionResult.ok(
            " ".join(s.text for s in result.data),
            provider=self.name,
            confidence=self._mean_confidence(result.data),
            duration=result.duration,
        )

    def read_adaptive(
        self, image: Any, region: BBox | None = None, language: str = "eng"
    ) -> VisionResult:
        """Read a region both normally and inverted, keeping the better result.

        Light text on a dark fill - every primary button in every modern UI -
        reads poorly in the normal pass. Reading twice and keeping whichever
        scored higher recovers those labels rather than dropping them.
        """

        normal = self.read(image, language, region)
        inverted = self.read(image, language, region, invert=True)

        if not normal.success and not inverted.success:
            return normal

        best = normal

        if not normal.success:
            best = inverted

        elif inverted.success:
            normal_score = self._score(normal.data)
            inverted_score = self._score(inverted.data)

            if inverted_score > normal_score:
                best = inverted
                best.limitations.append("read from an inverted (light-on-dark) region")

        return best

    def _score(self, spans: list[TextSpan]) -> float:
        """Total confident characters - rewards reading more, and reading it well."""

        return sum(len(s.text) * s.confidence for s in spans)

    def _mean_confidence(self, spans: list[TextSpan]) -> float:
        if not spans:
            return 0.0

        return round(sum(s.confidence for s in spans) / len(spans), 4)

    # ------------------------------------------------------------- grouping

    def phrases(self, spans: list[TextSpan], gap: int = WORD_GAP) -> list[TextSpan]:
        """Join words on the same line into phrases.

        "Sign in to continue" arrives as four separate words with four boxes;
        grounding needs the phrase, so adjacent words on a line are merged.
        """

        if not spans:
            return []

        by_line: dict[tuple[int, int], list[TextSpan]] = {}

        for span in spans:
            by_line.setdefault((span.block, span.line), []).append(span)

        out: list[TextSpan] = []

        for key in sorted(by_line):
            row = sorted(by_line[key], key=lambda s: s.bbox.x)
            group: list[TextSpan] = []

            for span in row:
                if group and (span.bbox.x - group[-1].bbox.right) > gap:
                    out.append(self._join(group))
                    group = []

                group.append(span)

            if group:
                out.append(self._join(group))

        return out

    def _join(self, group: list[TextSpan]) -> TextSpan:
        box = merge_boxes([s.bbox for s in group])

        return TextSpan(
            text=" ".join(s.text for s in group),
            bbox=box if box else group[0].bbox,
            confidence=round(sum(s.confidence for s in group) / len(group), 4),
            line=group[0].line,
            block=group[0].block,
        )


class ElementDetector(Provider):
    """Finds UI widgets from pixels, independently of any text they carry."""

    name = "cv-element-detector"
    capability = "UI_DETECTION"
    requires = ("cv2", "numpy", "PIL")

    def detect(
        self,
        image: Any,
        min_area: int = MIN_ELEMENT_AREA,
    ) -> VisionResult:
        """Locate rectangular widget candidates. Returns a list of BBox."""

        if image is None:
            return VisionResult.fail(
                INVALID_INPUT, "no image supplied", provider=self.name,
                recoverable=False,
            )

        def run():
            import cv2
            import numpy as np
            from PIL import Image

            picture = image

            if isinstance(picture, (str, bytes)):
                picture = Image.open(picture)

            frame = np.array(picture.convert("RGB"))
            grey = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)

            # Two complementary passes. Canny finds outlined controls (an empty
            # input box); adaptive threshold finds filled ones (a solid button)
            # whose interior gives no edge. Either alone misses half the UI.
            edges = cv2.Canny(cv2.GaussianBlur(grey, (5, 5), 0), 40, 140)
            edges = cv2.dilate(edges, np.ones((3, 3), np.uint8), iterations=1)

            binary = cv2.adaptiveThreshold(
                grey, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 21, 8
            )

            height, width = grey.shape[:2]
            found: list[tuple[BBox, float]] = []

            for source, weight in ((edges, 0.62), (binary, 0.55)):
                contours, _ = cv2.findContours(
                    source, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE
                )

                for contour in contours:
                    perimeter = cv2.arcLength(contour, True)
                    approx = cv2.approxPolyDP(contour, 0.02 * perimeter, True)
                    x, y, w, h = cv2.boundingRect(approx)

                    if w * h < min_area or w < MIN_ELEMENT_SIDE or h < MIN_ELEMENT_SIDE:
                        continue

                    # Ignore anything spanning almost the whole frame: that is
                    # the window itself or the background, not a widget.
                    if w > width * 0.97 and h > height * 0.97:
                        continue

                    extent = (w * h) / max(1, cv2.contourArea(contour))

                    # A widget is close to its bounding rectangle. A ragged
                    # contour with a large gap is texture or a text blob.
                    if extent > 2.2:
                        continue

                    rectangular = len(approx) == 4
                    score = weight + (0.2 if rectangular else 0.0)
                    found.append((BBox(x, y, w, h), round(min(0.95, score), 4)))

            return suppress_overlaps(found, threshold=0.4)

        return self.guard(run, timeout=25.0)

    def region_fill(self, image: Any, box: BBox) -> tuple[tuple[int, int, int], float]:
        """Mean colour and pixel spread of a region.

        The spread is what separates a filled control from a patch of text.
        A solid button is uniform (standard deviation around 25-30 even with a
        label on it); a line of text over a page background is not (65-85).
        An earlier version judged "filled" purely by distance from the page
        colour, which classified every dark word as a button.
        """

        try:
            import numpy as np
            from PIL import Image

            picture = image

            if isinstance(picture, (str, bytes)):
                picture = Image.open(picture)

            patch = np.array(
                picture.convert("RGB").crop((box.x, box.y, box.right, box.bottom))
            )

            if patch.size == 0:
                return (0, 0, 0), 0.0

            inset = max(1, min(patch.shape[0], patch.shape[1]) // 6)

            if patch.shape[0] > 2 * inset and patch.shape[1] > 2 * inset:
                patch = patch[inset:-inset, inset:-inset]

            flat = patch.reshape(-1, 3)
            mean = flat.mean(axis=0)
            spread = float(flat.std(axis=0).mean())

            return (int(mean[0]), int(mean[1]), int(mean[2])), round(spread, 2)

        except Exception:
            return (0, 0, 0), 0.0

    def dominant_colour(self, image: Any, box: BBox) -> tuple[int, int, int]:
        """Average colour of a region, used for "the blue button" grounding."""

        try:
            import numpy as np
            from PIL import Image

            picture = image

            if isinstance(picture, (str, bytes)):
                picture = Image.open(picture)

            patch = np.array(
                picture.convert("RGB").crop(
                    (box.x, box.y, box.right, box.bottom)
                )
            )

            if patch.size == 0:
                return (0, 0, 0)

            # Trim the border so the widget's own outline does not dominate.
            inset = max(1, min(patch.shape[0], patch.shape[1]) // 6)

            if patch.shape[0] > 2 * inset and patch.shape[1] > 2 * inset:
                patch = patch[inset:-inset, inset:-inset]

            mean = patch.reshape(-1, 3).mean(axis=0)

            return (int(mean[0]), int(mean[1]), int(mean[2]))

        except Exception:
            return (0, 0, 0)


def colour_name(rgb: tuple[int, int, int]) -> str:
    """Coarse colour label. Grounding needs "blue", not an RGB triple."""

    r, g, b = (int(v) for v in rgb)
    high = max(r, g, b)
    low = min(r, g, b)

    if high - low < 28:
        if high > 205:
            return "white"

        if high < 65:
            return "black"

        return "grey"

    if r == high:
        return "orange" if g > 110 and g > b + 40 else "red"

    if g == high:
        return "green"

    return "blue"


def classify(
    box: BBox,
    text: str,
    inner_text: list[TextSpan],
    nearby: list[TextSpan],
    colour: tuple[int, int, int],
    background: tuple[int, int, int] = (245, 245, 247),
    spread: float = 0.0,
) -> tuple[str, float, dict[str, Any]]:
    """Decide what a detected box is (sections 13 and 14).

    Uses shape, the text inside it, the text around it and how far its fill
    departs from the page background. Returns (kind, confidence, attributes)
    so the caller can see why, not just what.
    """

    label = str(text).strip()
    lowered = label.lower()

    # A filled button's white label is invisible to the whole-page OCR pass and
    # is recovered by a separate region read, which lands in ``text`` and not
    # in ``inner_text``. Testing only ``inner_text`` therefore sent every
    # primary button down the "empty box" branch and classified it as an input.
    has_text = bool(inner_text) or bool(label)
    aspect = box.aspect
    # A control is filled when its colour departs from the page AND its
    # pixels are uniform. Distance alone made every dark word a button,
    # because the mean colour of a text region also sits far from the page.
    distance = sum(abs(c - b) for c, b in zip(colour, background))
    uniform = spread <= 45.0 if spread else True
    filled = distance > 90 and uniform
    reasons: list[str] = []
    attributes: dict[str, Any] = {
        "colour": colour_name(colour),
        "filled": filled,
        "spread": spread,
    }

    # High-variance region with text and no uniform fill is prose, not a
    # control - decided before the button rules so a label cannot reach them.
    if has_text and spread > 55.0 and not filled:
        return "text", 0.55, {
            **attributes,
            "why": f"high pixel variance ({spread:.0f}) - text, not a filled control",
        }

    # Checkbox and radio: small and square.
    if 0.7 <= aspect <= 1.4 and box.width <= 40 and box.height <= 40:
        kind = "checkbox"
        reasons.append("small square")
        attributes["shape"] = "square"

        return kind, 0.62, {**attributes, "why": "; ".join(reasons)}

    # Icon: small, square-ish, no text.
    if 0.6 <= aspect <= 1.7 and box.width <= 64 and box.height <= 64 and not label:
        return "icon", 0.5, {**attributes, "why": "small, square and unlabelled"}

    # Button: a filled control whose text sits inside it and reads as an action.
    if filled and has_text:
        confidence = 0.62
        reasons.append("filled region containing its own text")

        if lowered in ACTION_WORDS or any(w in ACTION_WORDS for w in lowered.split()):
            confidence += 0.22
            reasons.append("text names an action")

        if 1.4 <= aspect <= 7.0:
            confidence += 0.08
            reasons.append("button-like proportions")

        attributes["destructive"] = any(
            word in lowered for word in DESTRUCTIVE_WORDS
        )
        attributes["action"] = lowered

        return "button", round(min(0.95, confidence), 4), {
            **attributes, "why": "; ".join(reasons)
        }

    # Unfilled but action-worded and text-bearing: a secondary/outline button.
    if has_text and lowered in ACTION_WORDS:
        return "button", 0.68, {
            **attributes,
            "destructive": any(w in lowered for w in DESTRUCTIVE_WORDS),
            "action": lowered,
            "why": "outlined control whose text names an action",
        }

    # A filled control whose label OCR could not read is still a button. An
    # input is characteristically unfilled, so without this an unreadable
    # two-letter button label ("Go") sent a solid blue control down the input
    # branch and it was reported as a text field.
    if filled and not has_text and 1.2 <= aspect <= 8.0:
        return "button", 0.55, {
            **attributes,
            "unlabelled": True,
            "why": "filled uniform control whose label could not be read",
        }

    # Input: an empty outlined box, wide and short, usually with a label above.
    if not has_text and 2.0 <= aspect <= 14.0 and 22 <= box.height <= 70:
        confidence = 0.55
        reasons.append("empty wide box")
        above = [
            s for s in nearby
            if s.bbox.bottom <= box.y and (box.y - s.bbox.bottom) < 40
            and abs(s.bbox.x - box.x) < 80
        ]

        if above:
            confidence += 0.18
            attributes["label"] = above[-1].text
            reasons.append(f"labelled '{above[-1].text}' above")

            if above[-1].text.strip().lower() in FIELD_WORDS:
                confidence += 0.1
                reasons.append("label names a known field")

        return "input", round(min(0.9, confidence), 4), {
            **attributes, "why": "; ".join(reasons)
        }

    # A filled wide box with text and a marker glyph is a dropdown.
    if has_text and 2.0 <= aspect <= 10.0 and not filled:
        return "dropdown", 0.5, {
            **attributes, "why": "outlined box with a value and no action word"
        }

    if has_text:
        return "label", 0.5, {**attributes, "why": "text with no control affordance"}

    return "container", 0.35, {**attributes, "why": "region with no identifying features"}
