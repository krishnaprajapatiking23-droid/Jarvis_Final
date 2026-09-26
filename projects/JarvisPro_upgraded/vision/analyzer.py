"""
==========================================
JARVIS PRO
Vision analyzer
==========================================

Roadmap sections 7 (full screen understanding), 8 (screenshot analysis),
17 (visual grounding), 21 (screen state), 22 (UI state comparison),
23 (visual action verification) and 24 (screen-change detection).

This is where located text and detected boxes become a screen the rest of
Jarvis can reason about.

The ordering matters and is not arbitrary. Elements are detected first, then
each element's own region is OCR'd separately, because reading a whole
screenshot in one pass loses light-on-dark button labels - the full-image pass
reads "gin" where the per-region pass reads "Login". Classification then sees
both the shape and its own text.

Grounding resolves a phrase like "the blue Submit button" to one element by
scoring several independent signals, and *refuses* when the top two candidates
are too close rather than picking arbitrarily. Section 17 forbids hardcoded
coordinates; nothing here carries any.
"""

from __future__ import annotations

import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from .perception import (
    DESTRUCTIVE_WORDS,
    ElementDetector,
    OCRProvider,
    TextSpan,
    classify,
    colour_name,
)
from .providers import INVALID_INPUT, VisionResult
from .types import BBox, Element

# Below this the two best grounding candidates are indistinguishable.
GROUNDING_MARGIN = 0.12

# A grounding result under this is not safe to act on without asking.
GROUNDING_FLOOR = 0.3

# Fraction of changed pixels below which a screen counts as unchanged.
PIXEL_CHANGE_FLOOR = 0.002

SPATIAL_WORDS = {
    "next to": "near", "beside": "near", "near": "near", "by": "near",
    "above": "above", "over": "above",
    "below": "below", "under": "below", "beneath": "below",
    "left of": "left", "right of": "right",
    "top": "top", "bottom": "bottom",
}

COLOUR_WORDS = ("red", "green", "blue", "orange", "white", "black", "grey", "gray")

KIND_WORDS = {
    "button": "button", "field": "input", "box": "input", "input": "input",
    "textbox": "input", "checkbox": "checkbox", "tickbox": "checkbox",
    "link": "link", "menu": "menu", "tab": "tab", "icon": "icon",
    "dropdown": "dropdown", "label": "label", "text": "text",
}


@dataclass
class ScreenObservation:
    """The structured result of understanding one screenshot (section 7)."""

    width: int
    height: int
    elements: list[Element] = field(default_factory=list)
    text_spans: list[TextSpan] = field(default_factory=list)
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    title: str = ""
    application: str = ""
    degraded: bool = True
    limitations: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    captured_at: float = field(default_factory=time.time)
    duration: float = 0.0

    def of_kind(self, kind: str) -> list[Element]:
        return [e for e in self.elements if e.kind == kind]

    @property
    def buttons(self) -> list[Element]:
        return self.of_kind("button")

    @property
    def inputs(self) -> list[Element]:
        return self.of_kind("input")

    @property
    def interactive(self) -> list[Element]:
        return [e for e in self.elements if e.interactive]

    def text(self) -> str:
        return " ".join(s.text for s in self.text_spans)

    def find_text(self, needle: str) -> list[TextSpan]:
        lowered = str(needle).strip().lower()

        return [s for s in self.text_spans if lowered in s.text.lower()]

    def element_by_id(self, element_id: str) -> Element | None:
        for element in self.elements:
            if element.id == element_id:
                return element

        return None

    def report(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "screen": {"width": self.width, "height": self.height},
            "title": self.title,
            "application": self.application,
            "elements": [e.report() for e in self.elements],
            "text": [s.report() for s in self.text_spans],
            "buttons": [e.report() for e in self.buttons],
            "inputs": [e.report() for e in self.inputs],
            "counts": {
                kind: len(self.of_kind(kind))
                for kind in sorted({e.kind for e in self.elements})
            },
            "degraded": self.degraded,
            "limitations": list(self.limitations),
            "sources": list(self.sources),
            "captured_at": self.captured_at,
            "duration": round(self.duration, 4),
        }


class ScreenAnalyzer:
    """Turns a screenshot into a :class:`ScreenObservation`."""

    def __init__(
        self,
        ocr: OCRProvider | None = None,
        detector: ElementDetector | None = None,
        vision_model: Any = None,
    ) -> None:
        self.ocr = ocr or OCRProvider()
        self.detector = detector or ElementDetector()
        self.vision_model = vision_model

    def analyze(
        self,
        image: Any,
        application: str = "",
        title: str = "",
        deep: bool = True,
    ) -> VisionResult:
        """Full screenshot analysis (section 8)."""

        if image is None:
            return VisionResult.fail(
                INVALID_INPUT, "no image supplied", provider="screen-analyzer",
                recoverable=False,
            )

        started = time.monotonic()

        try:
            from PIL import Image

            picture = Image.open(image) if isinstance(image, (str, bytes)) else image
            picture = picture.convert("RGB")

        except Exception as exc:
            return VisionResult.fail(
                INVALID_INPUT,
                f"image could not be opened: {type(exc).__name__}: {exc}",
                provider="screen-analyzer",
                recoverable=False,
            )

        width, height = picture.size
        sources: list[str] = []
        limitations: list[str] = []

        # 1. Whole-screen text, for reading and for labels that sit outside
        #    any detected control.
        page = self.ocr.read(picture)
        spans: list[TextSpan] = []

        if page.success:
            spans = self.ocr.phrases(page.data)
            sources.append("ocr")

        else:
            limitations.append(f"OCR unavailable: {page.message}")

        # 2. Widget candidates from the pixels, independent of the text.
        boxes: list[tuple[BBox, float]] = []
        found = self.detector.detect(picture)

        if found.success:
            boxes = found.data
            sources.append("cv")

        else:
            limitations.append(f"element detection unavailable: {found.message}")

        # 3. Per-element OCR. This is the step that recovers light-on-dark
        #    button labels; a single whole-image pass reads them wrongly.
        elements: list[Element] = []

        for box, shape_score in boxes:
            inner = [s for s in spans if box.contains_box(s.bbox.expand(-2) if
                     s.bbox.width > 4 and s.bbox.height > 4 else s.bbox)]
            label = " ".join(s.text for s in inner).strip()

            if deep and not label and box.area >= 1200 and self.ocr.available:
                region = self.ocr.read_adaptive(picture, region=box)

                if region.success and region.data:
                    label = " ".join(s.text for s in region.data).strip()

                    if label:
                        sources.append("ocr-region")

            colour, spread = self.detector.region_fill(picture, box)

            # A uniform, strongly coloured region is a filled control, and its
            # label is light-on-dark. The whole-page OCR pass reads those badly
            # ("Login" comes back as "gin"), so re-read the region adaptively
            # and keep it when it recovers more text - regardless of whether
            # the page pass already produced something.
            looks_filled = (
                spread <= 45.0
                and sum(abs(c - b) for c, b in zip(colour, (245, 245, 247))) > 90
            )

            if deep and looks_filled and box.area >= 1200 and self.ocr.available:
                region = self.ocr.read_adaptive(picture, region=box)

                if region.success and region.data:
                    recovered = " ".join(s.text for s in region.data).strip()

                    if len(recovered) > len(label):
                        label = recovered
                        sources.append("ocr-region")

            nearby = [
                s for s in spans
                if s.bbox.distance_to(box) < max(160, box.width)
                and not box.contains_box(s.bbox)
            ]

            kind, confidence, attributes = classify(
                box, label, inner, nearby, colour, spread=spread
            )

            elements.append(
                Element(
                    kind=kind,
                    bbox=box,
                    text=label,
                    confidence=round(min(0.95, (confidence + shape_score) / 2), 4),
                    source="+".join(sorted(set(s for s in sources if s.startswith("ocr") or s == "cv"))) or "cv",
                    attributes=attributes,
                )
            )

        # 3b. Drop boxes nested inside a control. The detector legitimately
        #     finds the text blob inside a button as its own rectangle, which
        #     produced two "Cancel" buttons at different coordinates and then
        #     made every grounding attempt ambiguous. Non-maximum suppression
        #     misses these because a small inner box overlaps its container at
        #     an IoU of only about 0.16. Containment is the right test, and it
        #     is applied only to controls so a genuine element inside a dialog
        #     is preserved.
        controls = [
            e for e in elements
            if e.kind in ("button", "input", "dropdown", "checkbox")
        ]
        nested: set[int] = set()

        for index, element in enumerate(elements):
            for container in controls:
                if container is element:
                    continue

                if container.bbox.contains_box(element.bbox) and (
                    element.bbox.area < container.bbox.area * 0.85
                ):
                    nested.add(index)

                    # The inner text is the container's label when the
                    # container has not read one of its own.
                    if element.text and not container.text:
                        container.text = element.text

                    break

        elements = [e for i, e in enumerate(elements) if i not in nested]

        # 3c. Two detections that resolve to the same stable id are the same
        #     thing found twice; keeping both puts duplicate ids in one
        #     observation and breaks id-based matching downstream.
        unique: dict[str, Element] = {}

        for element in elements:
            existing = unique.get(element.id)

            if existing is None or element.confidence > existing.confidence:
                unique[element.id] = element

        elements = list(unique.values())

        # 4. Text that belongs to no control is still content on the screen.
        for span in spans:
            if any(e.bbox.contains_box(span.bbox) for e in elements):
                continue

            if len(span.text.strip()) < 2:
                continue

            elements.append(
                Element(
                    kind="text",
                    bbox=span.bbox,
                    text=span.text,
                    confidence=span.confidence,
                    source="ocr",
                )
            )

        # 5. Honest capability statement. Without a vision model this is
        #    OCR plus computer vision, which section 62 forbids calling full
        #    visual understanding.
        degraded = True
        description = ""

        if self.vision_model is not None and getattr(self.vision_model, "available", False):
            described = self.vision_model.describe_image(
                picture, "Describe the application and layout visible here."
            )

            if described.success:
                degraded = False
                sources.append("vision-model")
                data = described.data
                description = (
                    data.get("description", "") if isinstance(data, dict) else str(data)
                )

            else:
                limitations.append(f"vision model failed: {described.message}")

        if degraded:
            limitations.append(
                "no vision model available - this observation is OCR plus "
                "computer vision, not full visual understanding; unlabelled "
                "graphics and semantic layout are not interpreted"
            )

        observation = ScreenObservation(
            width=width,
            height=height,
            elements=elements,
            text_spans=spans,
            title=title or self._guess_title(spans, width),
            application=application,
            degraded=degraded,
            limitations=limitations,
            sources=sorted(set(sources)),
            duration=time.monotonic() - started,
        )

        if description:
            observation.limitations = [
                l for l in observation.limitations if "no vision model" not in l
            ]

        result = VisionResult.ok(
            observation,
            provider="screen-analyzer",
            confidence=self._confidence(observation),
            duration=observation.duration,
            degraded=degraded,
            limitations=observation.limitations,
        )

        return result

    def _guess_title(self, spans: list[TextSpan], width: int) -> str:
        """The topmost text in the title-bar band, if any."""

        top = [s for s in spans if s.bbox.y < 50]

        if not top:
            return ""

        return min(top, key=lambda s: (s.bbox.y, s.bbox.x)).text

    def _confidence(self, observation: ScreenObservation) -> float:
        if not observation.elements:
            return 0.0

        mean = sum(e.confidence for e in observation.elements) / len(observation.elements)

        return round(mean * (0.75 if observation.degraded else 1.0), 4)


class VisualGrounding:
    """Resolves a natural-language reference to one on-screen element."""

    def parse(self, phrase: str) -> dict[str, Any]:
        """Pull the constraints out of a reference (section 17)."""

        text = str(phrase or "").strip().lower()
        wanted_kind = ""
        wanted_colour = ""
        relation = ""
        anchor = ""

        for word, kind in KIND_WORDS.items():
            if re.search(rf"\b{word}\b", text):
                wanted_kind = kind
                break

        for word in COLOUR_WORDS:
            if re.search(rf"\b{word}\b", text):
                wanted_colour = "grey" if word == "gray" else word
                break

        for word, rel in SPATIAL_WORDS.items():
            if word in text:
                relation = rel
                after = text.split(word, 1)[1].strip()
                anchor = re.sub(
                    r"^(the|a|an)\s+", "", after
                ).strip(" .?!")

                for junk in list(KIND_WORDS) + list(COLOUR_WORDS):
                    anchor = re.sub(rf"\b{junk}\b", "", anchor).strip()

                break

        # The quoted or capitalised part is the label being referred to.
        quoted = re.findall(r"[\"']([^\"']+)[\"']", str(phrase))
        label = quoted[0] if quoted else ""

        if not label:
            stripped = re.sub(
                r"\b(click|press|tap|select|find|locate|the|a|an|on|please|"
                r"button|field|box|input|checkbox|link|icon|menu|tab|dropdown|"
                r"label|text|textbox|tickbox)\b",
                " ",
                text,
            )

            if relation:
                stripped = stripped.split(
                    [w for w in SPATIAL_WORDS if w in text][0], 1
                )[0]

            for word in COLOUR_WORDS:
                stripped = re.sub(rf"\b{word}\b", " ", stripped)

            label = " ".join(stripped.split()).strip(" .?!")

        return {
            "label": label,
            "kind": wanted_kind,
            "colour": wanted_colour,
            "relation": relation,
            "anchor": anchor,
        }

    def ground(
        self, phrase: str, observation: ScreenObservation
    ) -> dict[str, Any]:
        """Find the element a phrase refers to, or refuse to guess."""

        wanted = self.parse(phrase)
        scored: list[tuple[float, Element, list[str]]] = []

        anchor_element = None

        if wanted["anchor"]:
            anchor_element = self._best_by_text(wanted["anchor"], observation)

        for element in observation.elements:
            score = 0.0
            why: list[str] = []

            # Text match is the strongest signal. An input carries no text of
            # its own - it is referred to by the label drawn beside it - so
            # the label is searched too, otherwise "the Username field" could
            # never resolve to the box it names.
            if wanted["label"]:
                text_score = max(
                    self._text_score(wanted["label"], element.text),
                    self._text_score(
                        wanted["label"], str(element.attributes.get("label", ""))
                    ),
                )

                if text_score > 0:
                    score += 0.5 * text_score
                    why.append(f"text match {text_score:.2f}")

                elif wanted["label"] and element.text:
                    score -= 0.05

            if wanted["kind"]:
                if element.kind == wanted["kind"]:
                    score += 0.25
                    why.append(f"is a {element.kind}")

                else:
                    score -= 0.2

            if wanted["colour"]:
                actual = element.attributes.get("colour", "")

                if actual == wanted["colour"]:
                    score += 0.2
                    why.append(f"is {actual}")

                elif actual:
                    score -= 0.15

            if wanted["relation"] and anchor_element is not None:
                if element.id == anchor_element.id:
                    continue

                spatial = self._spatial_score(
                    wanted["relation"], element, anchor_element
                )
                score += 0.3 * spatial

                if spatial > 0:
                    why.append(
                        f"{wanted['relation']} '{anchor_element.text or anchor_element.kind}'"
                    )

            # An instruction to click should prefer something clickable.
            if re.search(r"\b(click|press|tap|select)\b", str(phrase).lower()):
                if element.interactive:
                    score += 0.12
                    why.append("interactive")

                else:
                    score -= 0.18

            score += 0.08 * element.confidence

            if score > 0:
                scored.append((round(score, 4), element, why))

        scored.sort(key=lambda row: row[0], reverse=True)

        # Two scored entries that overlap heavily and carry the same text are
        # one widget detected twice, not a real ambiguity. Collapsing them
        # first keeps the ambiguity check meaningful.
        deduped: list[tuple[float, Element, list[str]]] = []

        for row in scored:
            duplicate = False

            for kept in deduped:
                same_text = row[1].text.strip().lower() == kept[1].text.strip().lower()

                if same_text and row[1].bbox.iou(kept[1].bbox) > 0.5:
                    duplicate = True
                    break

            if not duplicate:
                deduped.append(row)

        scored = deduped

        if not scored:
            return {
                "found": False,
                "reason": "nothing on screen matches that description",
                "parsed": wanted,
                "candidates": [],
            }

        best_score, best, why = scored[0]
        candidates = [
            {"id": e.id, "text": e.text, "type": e.kind, "score": s}
            for s, e, _ in scored[:4]
        ]

        if best_score < GROUNDING_FLOOR:
            return {
                "found": False,
                "reason": (
                    f"the best match scored only {best_score:.2f}, which is too "
                    f"weak to act on"
                ),
                "parsed": wanted,
                "candidates": candidates,
            }

        # Refuse an ambiguous reference rather than picking one (section 17).
        if len(scored) > 1 and (best_score - scored[1][0]) < GROUNDING_MARGIN:
            return {
                "found": False,
                "ambiguous": True,
                "reason": (
                    f"'{phrase}' matches at least two elements about equally "
                    f"well ({best.text or best.kind} and "
                    f"{scored[1][1].text or scored[1][1].kind}) - ask which"
                ),
                "parsed": wanted,
                "candidates": candidates,
            }

        return {
            "found": True,
            "element": best,
            "confidence": round(min(0.95, best_score), 4),
            "why": "; ".join(why),
            "parsed": wanted,
            "candidates": candidates,
        }

    def _text_score(self, wanted: str, actual: str) -> float:
        wanted = str(wanted).strip().lower()
        actual = str(actual).strip().lower()

        if not wanted or not actual:
            return 0.0

        if wanted == actual:
            return 1.0

        if wanted in actual or actual in wanted:
            return 0.8

        wanted_words = set(wanted.split())
        actual_words = set(actual.split())
        shared = wanted_words & actual_words

        if shared:
            return round(len(shared) / max(len(wanted_words), len(actual_words)), 4)

        return 0.0

    def _best_by_text(
        self, text: str, observation: ScreenObservation
    ) -> Element | None:
        best = None
        best_score = 0.0

        for element in observation.elements:
            score = self._text_score(text, element.text)

            if score > best_score:
                best_score = score
                best = element

        return best if best_score >= 0.5 else None

    def _spatial_score(self, relation: str, element: Element, anchor: Element) -> float:
        ex, ey = element.center
        ax, ay = anchor.center
        distance = element.bbox.distance_to(anchor.bbox)
        closeness = max(0.0, 1.0 - distance / 420.0)

        if relation == "near":
            return closeness

        if relation == "above":
            return closeness if element.bbox.bottom <= anchor.bbox.y + 6 else 0.0

        if relation == "below":
            return closeness if element.bbox.y >= anchor.bbox.bottom - 6 else 0.0

        if relation == "left":
            return closeness if element.bbox.right <= anchor.bbox.x + 6 else 0.0

        if relation == "right":
            return closeness if element.bbox.x >= anchor.bbox.right - 6 else 0.0

        return 0.0


@dataclass
class ScreenDiff:
    """What changed between two observations (section 22)."""

    added: list[Element] = field(default_factory=list)
    removed: list[Element] = field(default_factory=list)
    moved: list[dict[str, Any]] = field(default_factory=list)
    changed_text: list[dict[str, Any]] = field(default_factory=list)
    changed_state: list[dict[str, Any]] = field(default_factory=list)
    pixel_ratio: float = 0.0
    application_changed: bool = False
    title_changed: bool = False

    @property
    def changed(self) -> bool:
        return bool(
            self.added
            or self.removed
            or self.moved
            or self.changed_text
            or self.changed_state
            or self.application_changed
            or self.title_changed
        )

    def summary(self) -> str:
        parts = []

        for label, items in (
            ("added", self.added), ("removed", self.removed),
            ("moved", self.moved), ("text changed", self.changed_text),
            ("state changed", self.changed_state),
        ):
            if items:
                parts.append(f"{len(items)} {label}")

        return ", ".join(parts) if parts else "no structural change"

    def report(self) -> dict[str, Any]:
        return {
            "changed": self.changed,
            "summary": self.summary(),
            "added": [e.report() for e in self.added],
            "removed": [e.report() for e in self.removed],
            "moved": list(self.moved),
            "changed_text": list(self.changed_text),
            "changed_state": list(self.changed_state),
            "pixel_ratio": round(self.pixel_ratio, 5),
            "application_changed": self.application_changed,
            "title_changed": self.title_changed,
        }


class ScreenState:
    """Current and previous screen, with comparison and change detection."""

    def __init__(self, analyzer: ScreenAnalyzer | None = None) -> None:
        self.analyzer = analyzer or ScreenAnalyzer()
        self.current: ScreenObservation | None = None
        self.previous: ScreenObservation | None = None
        self._current_image: Any = None
        self._previous_image: Any = None

    def update(
        self, image: Any, application: str = "", title: str = ""
    ) -> VisionResult:
        result = self.analyzer.analyze(image, application=application, title=title)

        if not result.success:
            return result

        self.previous = self.current
        self._previous_image = self._current_image
        self.current = result.data
        self._current_image = image

        return result

    def compare(self) -> ScreenDiff:
        """Structural difference between the previous and current screens."""

        return self.diff(self.previous, self.current, self._previous_image,
                         self._current_image)

    def diff(
        self,
        before: ScreenObservation | None,
        after: ScreenObservation | None,
        before_image: Any = None,
        after_image: Any = None,
    ) -> ScreenDiff:
        result = ScreenDiff()

        if before is None or after is None:
            return result

        # Match elements by stable id first, then by text within a kind, so a
        # button that moved is reported as moved rather than as one removal
        # plus one addition.
        before_by_id = {e.id: e for e in before.elements}
        after_by_id = {e.id: e for e in after.elements}

        matched_after: set[str] = set()

        for element_id, old in before_by_id.items():
            new = after_by_id.get(element_id)

            if new is not None:
                matched_after.add(element_id)
                self._compare_pair(old, new, result)
                continue

            candidate = self._match_by_text(old, after.elements, matched_after)

            if candidate is not None:
                matched_after.add(candidate.id)

                if candidate.bbox != old.bbox:
                    result.moved.append(
                        {
                            "id": old.id,
                            "text": old.text,
                            "type": old.kind,
                            "from": old.bbox.report(),
                            "to": candidate.bbox.report(),
                            "distance": old.bbox.distance_to(candidate.bbox),
                        }
                    )

                self._compare_pair(old, candidate, result)
                continue

            result.removed.append(old)

        for element_id, new in after_by_id.items():
            if element_id not in matched_after:
                result.added.append(new)

        result.application_changed = (
            bool(before.application) and before.application != after.application
        )
        result.title_changed = (
            bool(before.title) and before.title != after.title
        )
        result.pixel_ratio = pixel_difference(before_image, after_image)

        return result

    def _match_by_text(
        self, old: Element, candidates: list[Element], taken: set[str]
    ) -> Element | None:
        """Find the same element after it moved.

        Text is the reliable signal, but an unlabelled control has none - and
        returning None there reported a moved button as one removal plus one
        addition. Geometry is the fallback: a control of the same kind and
        near-identical size is the same widget in a new place.
        """

        available = [e for e in candidates if e.id not in taken]
        wanted = old.text.strip().lower()

        if wanted:
            for element in available:
                if element.kind == old.kind and element.text.strip().lower() == wanted:
                    return element

            return None

        best = None
        best_score = 0.0

        for element in available:
            if element.kind != old.kind or element.text.strip():
                continue

            width_ratio = min(element.bbox.width, old.bbox.width) / max(
                1, max(element.bbox.width, old.bbox.width)
            )
            height_ratio = min(element.bbox.height, old.bbox.height) / max(
                1, max(element.bbox.height, old.bbox.height)
            )
            score = width_ratio * height_ratio

            if score > best_score:
                best_score = score
                best = element

        # Only a close size match counts; anything looser would pair unrelated
        # controls and hide a genuine addition.
        return best if best_score >= 0.9 else None

    def _compare_pair(self, old: Element, new: Element, result: ScreenDiff) -> None:
        if old.text.strip() != new.text.strip():
            result.changed_text.append(
                {
                    "id": new.id,
                    "type": new.kind,
                    "before": old.text,
                    "after": new.text,
                }
            )

        old_state = old.attributes.get("state") or old.enabled
        new_state = new.attributes.get("state") or new.enabled
        old_colour = old.attributes.get("colour")
        new_colour = new.attributes.get("colour")

        if old_state != new_state or old_colour != new_colour:
            result.changed_state.append(
                {
                    "id": new.id,
                    "type": new.kind,
                    "text": new.text,
                    "before": {"state": old_state, "colour": old_colour},
                    "after": {"state": new_state, "colour": new_colour},
                }
            )


def pixel_difference(before: Any, after: Any) -> float:
    """Fraction of pixels that differ (section 24).

    Cheap enough to run on every frame, which is what lets the pipeline skip
    the expensive analysis when nothing has changed.
    """

    if before is None or after is None:
        return 0.0

    try:
        import numpy as np
        from PIL import Image

        first = before if hasattr(before, "size") else Image.open(before)
        second = after if hasattr(after, "size") else Image.open(after)

        first = first.convert("L")
        second = second.convert("L")

        if first.size != second.size:
            return 1.0

        a = np.asarray(first, dtype=np.int16)
        b = np.asarray(second, dtype=np.int16)
        changed = np.abs(a - b) > 18

        return float(changed.sum()) / float(changed.size or 1)

    except Exception:
        return 0.0


def changed(before: Any, after: Any, threshold: float = PIXEL_CHANGE_FLOOR) -> bool:
    """Whether two frames differ enough to be worth analysing."""

    return pixel_difference(before, after) > threshold


def changed_regions(before: Any, after: Any, min_area: int = 400) -> list[BBox]:
    """Where the screen changed, so analysis can be limited to those areas."""

    try:
        import cv2
        import numpy as np
        from PIL import Image

        first = before if hasattr(before, "size") else Image.open(before)
        second = after if hasattr(after, "size") else Image.open(after)

        if first.size != second.size:
            return []

        a = np.asarray(first.convert("L"), dtype=np.uint8)
        b = np.asarray(second.convert("L"), dtype=np.uint8)
        delta = cv2.absdiff(a, b)
        _, mask = cv2.threshold(delta, 18, 255, cv2.THRESH_BINARY)
        mask = cv2.dilate(mask, np.ones((7, 7), np.uint8), iterations=2)

        contours, _ = cv2.findContours(
            mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        out: list[BBox] = []

        for contour in contours:
            x, y, w, h = cv2.boundingRect(contour)

            if w * h >= min_area:
                out.append(BBox(x, y, w, h))

        return sorted(out, key=lambda box: box.area, reverse=True)

    except Exception:
        return []
