"""
==========================================
JARVIS PRO
Vision test kit
==========================================

Roadmap sections 37 (test doubles), 38 (test dataset), 42 (end-to-end visual
control test) and 43 (document end-to-end test).

This renders deterministic UI screens and documents with Pillow so the vision
pipeline can be exercised without a display, a camera or a live application.

The important property is that these images are *real pixels*, not fixtures
with the answer attached. Tesseract genuinely reads them and the element
detector genuinely finds the shapes, so a test that passes here has exercised
the real OCR and real computer-vision path. What is known in advance is the
ground truth - :meth:`UIScreen.truth` reports where each widget was drawn - so
detection can be scored against it rather than merely inspected.

    screen = UIScreen().button("Submit", 740, 540).field("Search", 120, 200)
    image = screen.render()
    screen.truth()      # what should be found, for scoring

Nothing here is used at runtime. It exists so that "the detector found the
Submit button" is a measured claim.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

from .types import BBox

try:
    from PIL import Image, ImageDraw, ImageFont

    PILLOW = True

except Exception:  # pragma: no cover - exercised only without Pillow
    PILLOW = False
    Image = ImageDraw = ImageFont = None  # type: ignore

# Deliberately high contrast. OCR accuracy is not what is under test when the
# subject is element detection, so the text is made easy to read.
BACKGROUND = (245, 245, 247)
PANEL = (255, 255, 255)
BORDER = (170, 175, 185)
TEXT = (20, 20, 25)
MUTED = (120, 125, 135)
BUTTON = (58, 120, 220)
BUTTON_TEXT = (255, 255, 255)
DISABLED = (200, 203, 210)
DISABLED_TEXT = (140, 143, 150)
ACCENT = (32, 160, 90)
DANGER = (200, 60, 60)


def available() -> bool:
    return PILLOW


def _font(size: int = 16):
    """A real font at a usable size, falling back to the bitmap default.

    Pillow's default font is tiny and tesseract reads it poorly, so a truetype
    face is used when the host has one.
    """

    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "C:\\Windows\\Fonts\\arial.ttf",
    ]

    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)

            except Exception:
                continue

    return ImageFont.load_default()


@dataclass
class Widget:
    """One drawn control, with the ground truth of where it went."""

    kind: str
    text: str
    bbox: BBox
    enabled: bool = True
    state: str = ""
    colour: str = ""

    def report(self) -> dict[str, Any]:
        return {
            "type": self.kind,
            "text": self.text,
            "bbox": self.bbox.report(),
            "center": {"x": self.bbox.center[0], "y": self.bbox.center[1]},
            "enabled": self.enabled,
            "state": self.state,
            "colour": self.colour,
        }


class UIScreen:
    """A synthetic application window built from real drawn pixels."""

    def __init__(
        self,
        width: int = 900,
        height: int = 620,
        title: str = "VisionTestApp",
    ) -> None:
        if not PILLOW:
            raise RuntimeError("Pillow is required to render test screens")

        self.width = int(width)
        self.height = int(height)
        self.title = str(title)
        self.widgets: list[Widget] = []
        self._status = ""

    # ------------------------------------------------------------- widgets

    def button(
        self,
        label: str,
        x: int,
        y: int,
        width: int = 150,
        height: int = 46,
        enabled: bool = True,
        colour: str = "blue",
    ) -> "UIScreen":
        self.widgets.append(
            Widget("button", label, BBox(x, y, width, height), enabled, colour=colour)
        )

        return self

    def field(
        self,
        label: str,
        x: int,
        y: int,
        width: int = 320,
        height: int = 44,
        value: str = "",
    ) -> "UIScreen":
        """A labelled input. The label is drawn above the box, as in real UIs."""

        self.widgets.append(
            Widget("label", label, BBox(x, y - 26, max(80, len(label) * 11), 22))
        )
        self.widgets.append(
            Widget("input", value, BBox(x, y, width, height), state=label)
        )

        return self

    def checkbox(
        self, label: str, x: int, y: int, checked: bool = False
    ) -> "UIScreen":
        self.widgets.append(
            Widget(
                "checkbox",
                label,
                BBox(x, y, 24, 24),
                state="checked" if checked else "unchecked",
            )
        )
        self.widgets.append(
            Widget("label", label, BBox(x + 34, y + 2, max(80, len(label) * 11), 22))
        )

        return self

    def dropdown(
        self, label: str, x: int, y: int, width: int = 220, height: int = 42
    ) -> "UIScreen":
        self.widgets.append(Widget("dropdown", label, BBox(x, y, width, height)))

        return self

    def text(self, body: str, x: int, y: int, size: int = 16) -> "UIScreen":
        self.widgets.append(
            Widget("text", body, BBox(x, y, max(60, int(len(body) * size * 0.58)), size + 8))
        )

        return self

    def status(self, message: str) -> "UIScreen":
        self._status = str(message)

        return self

    # ------------------------------------------------------------- render

    def render(self):
        """Draw the screen and return a Pillow image."""

        image = Image.new("RGB", (self.width, self.height), BACKGROUND)
        draw = ImageDraw.Draw(image)

        title_font = _font(18)
        body_font = _font(16)
        button_font = _font(17)

        # Title bar.
        draw.rectangle([0, 0, self.width, 44], fill=PANEL, outline=BORDER)
        draw.text((18, 12), self.title, font=title_font, fill=TEXT)

        for widget in self.widgets:
            box = widget.bbox
            rect = [box.x, box.y, box.right, box.bottom]

            if widget.kind == "button":
                fill = BUTTON

                if widget.colour == "green":
                    fill = ACCENT

                elif widget.colour == "red":
                    fill = DANGER

                if not widget.enabled:
                    fill = DISABLED

                draw.rectangle(rect, fill=fill, outline=BORDER, width=2)
                self._centre_text(
                    draw,
                    box,
                    widget.text,
                    button_font,
                    DISABLED_TEXT if not widget.enabled else BUTTON_TEXT,
                )

            elif widget.kind == "input":
                draw.rectangle(rect, fill=PANEL, outline=BORDER, width=2)

                if widget.text:
                    draw.text(
                        (box.x + 12, box.y + box.height // 2 - 9),
                        widget.text,
                        font=body_font,
                        fill=TEXT,
                    )

            elif widget.kind == "checkbox":
                draw.rectangle(rect, fill=PANEL, outline=BORDER, width=2)

                if widget.state == "checked":
                    draw.line(
                        [box.x + 5, box.y + 12, box.x + 10, box.y + 18],
                        fill=ACCENT, width=3,
                    )
                    draw.line(
                        [box.x + 10, box.y + 18, box.x + 19, box.y + 6],
                        fill=ACCENT, width=3,
                    )

            elif widget.kind == "dropdown":
                draw.rectangle(rect, fill=PANEL, outline=BORDER, width=2)
                draw.text(
                    (box.x + 12, box.y + box.height // 2 - 9),
                    widget.text, font=body_font, fill=TEXT,
                )
                arrow = box.right - 22
                mid = box.y + box.height // 2
                draw.polygon(
                    [(arrow - 6, mid - 3), (arrow + 6, mid - 3), (arrow, mid + 5)],
                    fill=MUTED,
                )

            elif widget.kind in ("label", "text"):
                draw.text((box.x, box.y), widget.text, font=body_font, fill=TEXT)

        if self._status:
            draw.text(
                (18, self.height - 34), self._status, font=body_font, fill=ACCENT
            )

        return image

    def _centre_text(self, draw, box: BBox, text: str, font, fill) -> None:
        try:
            left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
            text_w, text_h = right - left, bottom - top

        except Exception:
            text_w, text_h = len(text) * 9, 16

        draw.text(
            (box.x + (box.width - text_w) // 2, box.y + (box.height - text_h) // 2 - 2),
            text,
            font=font,
            fill=fill,
        )

    def save(self, path: str) -> str:
        self.render().save(path)

        return path

    # ------------------------------------------------------------- truth

    def truth(self, kinds: tuple[str, ...] = ()) -> list[dict[str, Any]]:
        """Ground truth for scoring detection. Never used by the detector."""

        return [
            w.report() for w in self.widgets if not kinds or w.kind in kinds
        ]

    def find(self, text: str) -> Widget | None:
        for widget in self.widgets:
            if widget.text.strip().lower() == str(text).strip().lower():
                return widget

        return None

    def clone(self) -> "UIScreen":
        copy = UIScreen(self.width, self.height, self.title)
        copy.widgets = [
            Widget(w.kind, w.text, w.bbox, w.enabled, w.state, w.colour)
            for w in self.widgets
        ]
        copy._status = self._status

        return copy


# --------------------------------------------------------------------------
# Prebuilt scenes. Section 38 asks for a dataset covering UI screens, state
# changes and documents; these are the fixtures the tests are scored against.


def login_screen(submit_enabled: bool = True) -> UIScreen:
    return (
        UIScreen(title="VisionTestApp")
        .text("Sign in to continue", 60, 80, size=20)
        .field("Username", 60, 160, width=360)
        .field("Password", 60, 260, width=360)
        .checkbox("Remember me", 60, 340, checked=False)
        .button("Login", 60, 400, enabled=submit_enabled)
        .button("Cancel", 240, 400, colour="red")
    )


def form_screen(text_value: str = "", status: str = "Ready") -> UIScreen:
    return (
        UIScreen(title="VisionTestApp")
        .text("Search the catalogue", 60, 80, size=20)
        .field("Search", 60, 160, width=420, value=text_value)
        .dropdown("Category", 60, 250)
        .checkbox("Notifications", 60, 330, checked=False)
        .button("Submit", 60, 400, colour="green")
        .status(status)
    )


def dialog_screen() -> UIScreen:
    return (
        UIScreen(title="VisionTestApp")
        .text("Delete this file?", 60, 80, size=20)
        .text("This action cannot be undone.", 60, 130)
        .button("Delete", 60, 200, colour="red")
        .button("Keep", 240, 200)
    )


def state_pair() -> tuple[UIScreen, UIScreen]:
    """Before/after screens differing in exactly three known ways.

    The differences are: the Submit button becomes enabled, the search field
    gains text, and a confirmation line appears. Section 44 requires the
    comparison engine to tell these apart from no change at all.
    """

    before = (
        UIScreen(title="VisionTestApp")
        .field("Search", 60, 160, width=420)
        .button("Submit", 60, 300, enabled=False)
        .status("Ready")
    )

    after = (
        UIScreen(title="VisionTestApp")
        .field("Search", 60, 160, width=420, value="hello")
        .button("Submit", 60, 300, enabled=True)
        .text("Saved successfully", 60, 380)
        .status("Done")
    )

    return before, after


class Document:
    """A deterministic multi-page document with known field positions."""

    def __init__(self, width: int = 860, height: int = 1100) -> None:
        if not PILLOW:
            raise RuntimeError("Pillow is required to render test documents")

        self.width = int(width)
        self.height = int(height)
        self.lines: list[tuple[str, int, int, int]] = []
        self.rules: list[BBox] = []
        self._fields: dict[str, BBox] = {}

    def line(self, text: str, x: int, y: int, size: int = 18) -> "Document":
        self.lines.append((str(text), x, y, size))

        return self

    def field(self, name: str, text: str, x: int, y: int, size: int = 18) -> "Document":
        """A line whose position is recorded as ground truth."""

        self.lines.append((str(text), x, y, size))
        self._fields[str(name)] = BBox(
            x, y, max(60, int(len(str(text)) * size * 0.58)), size + 8
        )

        return self

    def rule(self, x: int, y: int, width: int) -> "Document":
        self.rules.append(BBox(x, y, width, 2))

        return self

    def render(self):
        image = Image.new("RGB", (self.width, self.height), (255, 255, 255))
        draw = ImageDraw.Draw(image)

        for text, x, y, size in self.lines:
            draw.text((x, y), text, font=_font(size), fill=(15, 15, 20))

        for rule in self.rules:
            draw.rectangle(
                [rule.x, rule.y, rule.right, rule.bottom], fill=(140, 140, 150)
            )

        return image

    def truth(self) -> dict[str, dict[str, Any]]:
        return {name: box.report() for name, box in self._fields.items()}

    def save(self, path: str) -> str:
        self.render().save(path)

        return path


def invoice() -> Document:
    """An invoice with a known total, date and signature area."""

    return (
        Document()
        .line("ACME SUPPLIES LIMITED", 60, 60, size=26)
        .field("invoice_number", "Invoice No: INV-2026-0417", 60, 130)
        .field("date", "Date: 14 March 2026", 60, 170)
        .field("due_date", "Due Date: 28 March 2026", 60, 210)
        .rule(60, 260, 740)
        .line("Description", 60, 290, size=18)
        .line("Quantity", 420, 290, size=18)
        .line("Amount", 620, 290, size=18)
        .rule(60, 320, 740)
        .line("Steel brackets", 60, 350)
        .line("40", 420, 350)
        .line("1200.00", 620, 350)
        .line("Mounting plates", 60, 390)
        .line("15", 420, 390)
        .line("450.00", 620, 390)
        .line("Delivery", 60, 430)
        .line("1", 420, 430)
        .line("85.50", 620, 430)
        .rule(60, 470, 740)
        .field("subtotal", "Subtotal: 1735.50", 420, 500)
        .field("tax", "Tax at 20 percent: 347.10", 420, 540)
        .field("total", "Total Due: 2082.60", 420, 590, size=22)
        .rule(60, 700, 300)
        .field("signature", "Authorised Signature", 60, 710, size=14)
    )
