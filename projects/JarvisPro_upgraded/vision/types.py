"""
==========================================
JARVIS PRO
Vision core types
==========================================

Roadmap sections 15 (element identification) and 16 (coordinate detection).

Three things live here because everything else in the vision layer depends on
them: the geometry (:class:`BBox`), the thing detected (:class:`Element`), and
the coordinate conversion between what a screenshot says and where the mouse
must actually go (:class:`CoordinateSpace`).

The coordinate work is the part that quietly breaks on real machines. A
screenshot on a 150%-scaled Windows display is captured at physical pixel
resolution, but the pointer is addressed in logical coordinates - so clicking
the raw screenshot coordinate lands a third of the way down the screen from the
button. Section 16 says never assume 100% scaling, so scaling is a required
part of the conversion, not an optional correction.
"""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass, field
from typing import Any, Iterable

# What an element can be. Section 13 lists the UI kinds that must be told apart.
ELEMENT_KINDS = (
    "button",
    "text",
    "label",
    "link",
    "input",
    "checkbox",
    "radio",
    "dropdown",
    "tab",
    "list",
    "menu",
    "dialog",
    "slider",
    "scrollarea",
    "toolbar",
    "icon",
    "image",
    "window",
    "container",
    "unknown",
)

# Kinds a user can act on. Used by grounding and control to refuse to "click"
# something that is only a label.
INTERACTIVE_KINDS = (
    "button",
    "link",
    "input",
    "checkbox",
    "radio",
    "dropdown",
    "tab",
    "slider",
    "menu",
    "icon",
)


@dataclass(frozen=True)
class BBox:
    """An axis-aligned box in image pixels."""

    x: int
    y: int
    width: int
    height: int

    def __post_init__(self) -> None:
        if self.width < 0 or self.height < 0:
            raise ValueError(f"negative box size: {self.width}x{self.height}")

    @property
    def right(self) -> int:
        return self.x + self.width

    @property
    def bottom(self) -> int:
        return self.y + self.height

    @property
    def area(self) -> int:
        return self.width * self.height

    @property
    def center(self) -> tuple[int, int]:
        return (self.x + self.width // 2, self.y + self.height // 2)

    @property
    def aspect(self) -> float:
        return self.width / self.height if self.height else 0.0

    def contains(self, x: int, y: int) -> bool:
        return self.x <= x < self.right and self.y <= y < self.bottom

    def contains_box(self, other: "BBox") -> bool:
        return (
            self.x <= other.x
            and self.y <= other.y
            and self.right >= other.right
            and self.bottom >= other.bottom
        )

    def intersects(self, other: "BBox") -> bool:
        return not (
            self.right <= other.x
            or other.right <= self.x
            or self.bottom <= other.y
            or other.bottom <= self.y
        )

    def intersection(self, other: "BBox") -> "BBox | None":
        if not self.intersects(other):
            return None

        x = max(self.x, other.x)
        y = max(self.y, other.y)

        return BBox(x, y, min(self.right, other.right) - x, min(self.bottom, other.bottom) - y)

    def iou(self, other: "BBox") -> float:
        """Intersection over union - the standard detection overlap measure."""

        overlap = self.intersection(other)

        if overlap is None:
            return 0.0

        union = self.area + other.area - overlap.area

        return round(overlap.area / union, 4) if union else 0.0

    def distance_to(self, other: "BBox") -> float:
        """Centre-to-centre distance, used for spatial relationships."""

        ax, ay = self.center
        bx, by = other.center

        return round(math.hypot(ax - bx, ay - by), 2)

    def expand(self, margin: int) -> "BBox":
        return BBox(
            max(0, self.x - margin),
            max(0, self.y - margin),
            self.width + 2 * margin,
            self.height + 2 * margin,
        )

    def scaled(self, factor: float) -> "BBox":
        return BBox(
            int(round(self.x * factor)),
            int(round(self.y * factor)),
            int(round(self.width * factor)),
            int(round(self.height * factor)),
        )

    def translated(self, dx: int, dy: int) -> "BBox":
        return BBox(self.x + dx, self.y + dy, self.width, self.height)

    def report(self) -> dict[str, Any]:
        cx, cy = self.center

        return {
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
            "center": {"x": cx, "y": cy},
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BBox":
        return cls(
            int(data.get("x", 0)),
            int(data.get("y", 0)),
            int(data.get("width", 0)),
            int(data.get("height", 0)),
        )

    @classmethod
    def from_corners(cls, x1: int, y1: int, x2: int, y2: int) -> "BBox":
        return cls(min(x1, x2), min(y1, y2), abs(x2 - x1), abs(y2 - y1))


def merge_boxes(boxes: Iterable[BBox]) -> BBox | None:
    """Smallest box containing all of the given boxes."""

    boxes = list(boxes)

    if not boxes:
        return None

    return BBox.from_corners(
        min(b.x for b in boxes),
        min(b.y for b in boxes),
        max(b.right for b in boxes),
        max(b.bottom for b in boxes),
    )


def suppress_overlaps(
    items: list[tuple[BBox, float]], threshold: float = 0.45
) -> list[tuple[BBox, float]]:
    """Non-maximum suppression: keep the strongest of each overlapping cluster.

    Detectors that scan an image return the same element several times at
    slightly different offsets. Without this, one button becomes five.
    """

    ordered = sorted(items, key=lambda row: row[1], reverse=True)
    kept: list[tuple[BBox, float]] = []

    for box, score in ordered:
        if any(box.iou(other) > threshold for other, _ in kept):
            continue

        kept.append((box, score))

    return kept


@dataclass
class Element:
    """One thing identified on screen, with where it is and how sure we are."""

    kind: str
    bbox: BBox
    text: str = ""
    confidence: float = 0.5
    id: str = ""
    source: str = "unknown"
    interactive: bool | None = None
    enabled: bool = True
    attributes: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.kind not in ELEMENT_KINDS:
            self.kind = "unknown"

        if self.interactive is None:
            self.interactive = self.kind in INTERACTIVE_KINDS

        if not self.id:
            self.id = self.stable_id()

    def stable_id(self) -> str:
        """An id that stays the same for the same element across captures.

        Derived from what the element *is* rather than a counter, so a
        re-scan of an unchanged screen produces matching ids and the state
        comparison in section 22 can tell "same element" from "new element".
        Position is quantised to a 16px grid so a one-pixel jitter in
        detection does not mint a new identity.
        """

        grid_x = self.bbox.x // 16
        grid_y = self.bbox.y // 16
        seed = f"{self.kind}|{self.text.strip().lower()}|{grid_x}|{grid_y}"

        return "el_" + uuid.uuid5(uuid.NAMESPACE_OID, seed).hex[:10]

    @property
    def center(self) -> tuple[int, int]:
        return self.bbox.center

    def report(self) -> dict[str, Any]:
        cx, cy = self.center

        return {
            "id": self.id,
            "type": self.kind,
            "text": self.text,
            "bbox": self.bbox.report(),
            "center": {"x": cx, "y": cy},
            "confidence": round(float(self.confidence), 4),
            "source": self.source,
            "interactive": bool(self.interactive),
            "enabled": bool(self.enabled),
            "attributes": dict(self.attributes),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Element":
        return cls(
            kind=str(data.get("type", data.get("kind", "unknown"))),
            bbox=BBox.from_dict(data.get("bbox") or {}),
            text=str(data.get("text", "")),
            confidence=float(data.get("confidence", 0.5)),
            id=str(data.get("id", "")),
            source=str(data.get("source", "unknown")),
            interactive=data.get("interactive"),
            enabled=bool(data.get("enabled", True)),
            attributes=dict(data.get("attributes") or {}),
        )


@dataclass
class CoordinateSpace:
    """Converts between screenshot pixels and where the pointer must go.

    ``scale`` is the display scaling factor (1.25 for 125%, 2.0 for a Retina
    panel). ``origin`` is the monitor's top-left in the virtual desktop, which
    is negative for a monitor placed left of the primary one.
    """

    width: int
    height: int
    scale: float = 1.0
    origin: tuple[int, int] = (0, 0)
    monitor: str = "primary"

    def __post_init__(self) -> None:
        if self.scale <= 0:
            raise ValueError(f"display scale must be positive, got {self.scale}")

        if self.width <= 0 or self.height <= 0:
            raise ValueError(f"invalid screen size: {self.width}x{self.height}")

    @property
    def logical_size(self) -> tuple[int, int]:
        """Size in the units the pointer is addressed in."""

        return (int(self.width / self.scale), int(self.height / self.scale))

    def to_screen(self, x: int, y: int) -> tuple[int, int]:
        """Screenshot pixel -> absolute virtual-desktop coordinate.

        Divides by the scale factor: a screenshot is captured in physical
        pixels but the pointer is addressed logically, so on a 150% display
        the raw screenshot coordinate would land a third of the way down the
        screen from the intended target.
        """

        return (
            int(round(x / self.scale)) + self.origin[0],
            int(round(y / self.scale)) + self.origin[1],
        )

    def to_image(self, screen_x: int, screen_y: int) -> tuple[int, int]:
        """Absolute screen coordinate -> screenshot pixel."""

        return (
            int(round((screen_x - self.origin[0]) * self.scale)),
            int(round((screen_y - self.origin[1]) * self.scale)),
        )

    def to_window(self, x: int, y: int, window: BBox) -> tuple[int, int]:
        """Screenshot pixel -> coordinate relative to a window's top-left."""

        return (x - window.x, y - window.y)

    def from_window(self, x: int, y: int, window: BBox) -> tuple[int, int]:
        return (x + window.x, y + window.y)

    def click_point(self, element: Element) -> tuple[int, int]:
        """Where to actually click for an element, in screen coordinates."""

        return self.to_screen(*element.center)

    def contains(self, x: int, y: int) -> bool:
        return 0 <= x < self.width and 0 <= y < self.height

    def clamp(self, x: int, y: int) -> tuple[int, int]:
        return (
            max(0, min(self.width - 1, x)),
            max(0, min(self.height - 1, y)),
        )

    def report(self) -> dict[str, Any]:
        return {
            "width": self.width,
            "height": self.height,
            "scale": self.scale,
            "origin": {"x": self.origin[0], "y": self.origin[1]},
            "logical_size": {
                "width": self.logical_size[0],
                "height": self.logical_size[1],
            },
            "monitor": self.monitor,
        }


class MonitorLayout:
    """Several monitors in one virtual desktop (section 16)."""

    def __init__(self, spaces: list[CoordinateSpace] | None = None) -> None:
        self.spaces = list(spaces or [])

    def add(self, space: CoordinateSpace) -> "MonitorLayout":
        self.spaces.append(space)

        return self

    def primary(self) -> CoordinateSpace | None:
        for space in self.spaces:
            if space.monitor == "primary":
                return space

        return self.spaces[0] if self.spaces else None

    def for_point(self, screen_x: int, screen_y: int) -> CoordinateSpace | None:
        """Which monitor a virtual-desktop coordinate falls on."""

        for space in self.spaces:
            left, top = space.origin
            logical_w, logical_h = space.logical_size

            if left <= screen_x < left + logical_w and top <= screen_y < top + logical_h:
                return space

        return None

    def virtual_bounds(self) -> BBox | None:
        """The rectangle covering every monitor, including negative origins."""

        if not self.spaces:
            return None

        lefts, tops, rights, bottoms = [], [], [], []

        for space in self.spaces:
            left, top = space.origin
            logical_w, logical_h = space.logical_size
            lefts.append(left)
            tops.append(top)
            rights.append(left + logical_w)
            bottoms.append(top + logical_h)

        # A monitor left of or above the primary has a negative origin, so the
        # bounds must be built from corners rather than assumed to start at 0.
        return BBox.from_corners(min(lefts), min(tops), max(rights), max(bottoms))

    def report(self) -> dict[str, Any]:
        bounds = self.virtual_bounds()

        return {
            "monitors": [s.report() for s in self.spaces],
            "count": len(self.spaces),
            "virtual_bounds": bounds.report() if bounds else None,
        }
