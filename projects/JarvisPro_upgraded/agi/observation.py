"""
==========================================
JARVIS PRO
AGI observation interface
==========================================

Roadmap sections 50 (cross-modal reasoning), 51 (vision + language),
52 (voice + language) and 57 (environment + reasoning).

Every modality converts to one structured :class:`Observation` so the reasoning
layer never branches on where information came from. Text, voice, vision, files,
code and system state all arrive in the same shape.

The honesty requirement in section 51 is enforced mechanically rather than by
convention. An :class:`Observation` records which *provider* produced it and
sets ``degraded`` when the real model was unavailable - so a vision observation
backed only by OCR reports ``degraded=True`` and a reduced confidence, and
:meth:`capability_report` states plainly which modalities are actually live in
this environment rather than claiming they all are.

    from agi.observation import observe

    obs = observe.text("open the report")
    obs = observe.vision(ocr_text="Total: 42")   # degraded, says so
"""

from __future__ import annotations

import os
import platform
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

TEXT = "text"
VOICE = "voice"
VISION = "vision"
SCREEN = "screen"
FILE = "file"
CODE = "code"
SYSTEM = "system"
BROWSER = "browser"

MODALITIES = (TEXT, VOICE, VISION, SCREEN, FILE, CODE, SYSTEM, BROWSER)


@dataclass
class Observation:
    """One structured percept, whatever produced it."""

    modality: str
    content: str
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    elements: list[dict[str, Any]] = field(default_factory=list)
    entities: list[str] = field(default_factory=list)
    confidence: float = 0.5
    provider: str = "none"
    degraded: bool = False
    limitations: list[str] = field(default_factory=list)
    at: float = field(default_factory=time.time)

    def usable(self) -> bool:
        return bool(self.content.strip()) and self.confidence > 0.2

    def report(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "modality": self.modality,
            "content": self.content[:2000],
            "elements": self.elements[:50],
            "entities": list(self.entities),
            "confidence": round(float(self.confidence), 4),
            "provider": self.provider,
            "degraded": self.degraded,
            "limitations": list(self.limitations),
            "at": self.at,
        }


def _entities(text: str) -> list[str]:
    """Pull out concrete referents: paths, apps, quoted names, URLs."""

    found: list[str] = []
    text = str(text or "")

    found.extend(re.findall(r"https?://[^\s<>\"']+", text))
    found.extend(re.findall(r"[A-Za-z]:\\[^\s\"'<>|]+", text))
    found.extend(re.findall(r"(?:^|\s)(/[\w./-]+)", text))
    found.extend(re.findall(r"\b[\w-]+\.(?:py|md|txt|json|csv|pdf|docx|xlsx|html|js|zip)\b", text))
    found.extend(re.findall(r"[\"']([^\"']{2,40})[\"']", text))

    seen: list[str] = []

    for item in found:
        cleaned = str(item).strip()

        if cleaned and cleaned not in seen:
            seen.append(cleaned)

    return seen[:20]


class ObservationInterface:
    """Converts every input modality into the one structure reasoning uses."""

    def __init__(self) -> None:
        self._providers: dict[str, Callable[..., Any]] = {}

    # ------------------------------------------------------------ providers

    def register_provider(self, modality: str, provider: Callable[..., Any]) -> bool:
        """Attach a real backend for a modality (a vision model, an STT engine)."""

        if modality not in MODALITIES:
            raise ValueError(f"unknown modality: {modality}")

        self._providers[modality] = provider

        return True

    def has_provider(self, modality: str) -> bool:
        return modality in self._providers

    # ------------------------------------------------------------ modalities

    def text(self, content: str, source: str = "user") -> Observation:
        body = str(content or "")

        return Observation(
            modality=TEXT,
            content=body,
            entities=_entities(body),
            confidence=1.0 if body.strip() else 0.0,
            provider=source,
        )

    def voice(
        self,
        transcript: str,
        asr_confidence: float = 0.7,
        partial: bool = False,
        provider: str = "asr",
    ) -> Observation:
        """Voice becomes the same structure as text (section 52).

        The transcript's own confidence is carried through rather than
        discarded, so downstream reasoning knows a mishearing is possible.
        """

        body = str(transcript or "")
        limitations: list[str] = []

        if partial:
            limitations.append("partial transcript - the utterance may be incomplete")

        if asr_confidence < 0.6:
            limitations.append("low transcription confidence - the wording may be wrong")

        return Observation(
            modality=VOICE,
            content=body,
            elements=[{"partial": bool(partial), "asr_confidence": float(asr_confidence)}],
            entities=_entities(body),
            confidence=0.0 if not body.strip() else round(float(asr_confidence), 4),
            provider=provider,
            degraded=bool(partial or asr_confidence < 0.6),
            limitations=limitations,
        )

    def vision(
        self,
        ocr_text: str = "",
        objects: list[dict[str, Any]] | None = None,
        layout: list[dict[str, Any]] | None = None,
        model_description: str = "",
        provider: str = "",
        image_path: str = "",
    ) -> Observation:
        """Vision observation with an honest account of what produced it.

        If a real vision model supplied ``model_description``, confidence is
        high and ``degraded`` is False. If only OCR text is available, the
        observation says so - section 51 forbids presenting OCR as visual
        understanding.
        """

        elements: list[dict[str, Any]] = []

        if ocr_text:
            elements.append({"type": "ocr", "text": str(ocr_text)[:2000]})

        if objects:
            elements.append({"type": "objects", "items": list(objects)[:50]})

        if layout:
            elements.append({"type": "layout", "items": list(layout)[:50]})

        if image_path:
            elements.append({"type": "source", "path": str(image_path)})

        has_model = bool(str(model_description).strip())
        body = str(model_description or ocr_text or "")
        limitations: list[str] = []

        if not has_model:
            limitations.append(
                "no vision model available - this is OCR text only, not visual "
                "understanding; spatial relationships and unlabelled elements "
                "are not observed"
            )

        if not body.strip():
            limitations.append("nothing legible was extracted from the image")

        return Observation(
            modality=VISION,
            content=body,
            elements=elements,
            entities=_entities(body),
            confidence=(0.8 if has_model else (0.4 if ocr_text else 0.0)),
            provider=provider or ("vision-model" if has_model else "ocr"),
            degraded=not has_model,
            limitations=limitations,
        )

    def screen(
        self,
        ocr_text: str = "",
        windows: list[dict[str, Any]] | None = None,
        model_description: str = "",
        provider: str = "",
    ) -> Observation:
        observation = self.vision(
            ocr_text=ocr_text,
            objects=windows,
            model_description=model_description,
            provider=provider,
        )
        observation.modality = SCREEN

        return observation

    def file(self, path: str, content: str = "", read: bool = False) -> Observation:
        """Observe a file. Existence is checked, not assumed."""

        exists = os.path.exists(path) if path else False
        limitations: list[str] = []
        body = str(content or "")

        if read and exists and not body:
            try:
                with open(path, "r", encoding="utf-8", errors="replace") as handle:
                    body = handle.read(20000)

            except OSError as exc:
                limitations.append(f"could not read: {exc}")

        if not exists:
            limitations.append("the path does not exist on this machine")

        return Observation(
            modality=FILE,
            content=body,
            elements=[
                {
                    "path": str(path),
                    "exists": exists,
                    "size": os.path.getsize(path) if exists and os.path.isfile(path) else 0,
                    "is_dir": os.path.isdir(path) if exists else False,
                }
            ],
            entities=[str(path)] if path else [],
            confidence=0.95 if exists else 0.9,
            provider="filesystem",
            limitations=limitations,
        )

    def code(self, source: str, language: str = "python", path: str = "") -> Observation:
        """Structural observation of code (section 53)."""

        body = str(source or "")
        elements: list[dict[str, Any]] = []

        if language == "python":
            try:
                import ast

                tree = ast.parse(body)
                functions = [
                    n.name for n in ast.walk(tree)
                    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                ]
                classes = [n.name for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
                imports: list[str] = []

                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        imports.extend(a.name for a in node.names)

                    elif isinstance(node, ast.ImportFrom) and node.module:
                        imports.append(node.module)

                elements.append(
                    {
                        "type": "structure",
                        "functions": functions[:60],
                        "classes": classes[:40],
                        "imports": sorted(set(imports))[:40],
                        "parsed": True,
                    }
                )

            except SyntaxError as exc:
                elements.append(
                    {
                        "type": "structure",
                        "parsed": False,
                        "syntax_error": f"line {exc.lineno}: {exc.msg}",
                    }
                )

        return Observation(
            modality=CODE,
            content=body[:8000],
            elements=elements,
            entities=[path] if path else [],
            confidence=0.9,
            provider=f"static-analysis:{language}",
        )

    def system(self) -> Observation:
        """Observe the real machine, not an assumed one (section 32)."""

        facts: dict[str, Any] = {
            "platform": platform.system(),
            "release": platform.release(),
            "python": platform.python_version(),
            "cwd": os.getcwd(),
        }
        limitations: list[str] = []

        try:
            import shutil

            usage = shutil.disk_usage(os.getcwd())
            facts["disk_free_gb"] = round(usage.free / 1e9, 2)

        except Exception as exc:
            limitations.append(f"disk usage unavailable: {exc}")

        try:
            import psutil  # type: ignore

            facts["cpu_percent"] = psutil.cpu_percent(interval=0.1)
            facts["memory_percent"] = psutil.virtual_memory().percent

        except Exception:
            limitations.append(
                "psutil not available - live CPU and memory figures are not observed"
            )

        return Observation(
            modality=SYSTEM,
            content="; ".join(f"{k}={v}" for k, v in facts.items()),
            elements=[{"type": "system", **facts}],
            confidence=0.95,
            provider="platform",
            degraded=bool(limitations),
            limitations=limitations,
        )

    # ------------------------------------------------------------ fusion

    def fuse(self, observations: list[Observation]) -> Observation:
        """Merge observations from different modalities into one percept.

        This is what makes "here is a screenshot, now do X" a single reasoning
        input rather than two disconnected ones (section 50).
        """

        usable = [o for o in observations if o and o.usable()]

        if not usable:
            return Observation(
                modality=TEXT,
                content="",
                confidence=0.0,
                provider="fusion",
                degraded=True,
                limitations=["no usable observation was supplied"],
            )

        parts: list[str] = []
        elements: list[dict[str, Any]] = []
        entities: list[str] = []
        limitations: list[str] = []

        for observation in usable:
            parts.append(f"[{observation.modality}] {observation.content.strip()}")
            elements.extend(observation.elements)
            limitations.extend(observation.limitations)

            for entity in observation.entities:
                if entity not in entities:
                    entities.append(entity)

        # Joint confidence is the weakest link, not the average: a confident
        # instruction paired with a degraded image is not a confident percept.
        confidence = min(o.confidence for o in usable)

        return Observation(
            modality="fused",
            content="\n".join(parts),
            elements=elements[:80],
            entities=entities[:30],
            confidence=round(confidence, 4),
            provider="fusion:" + ",".join(sorted({o.modality for o in usable})),
            degraded=any(o.degraded for o in usable),
            limitations=limitations,
        )

    # ------------------------------------------------------------ honesty

    def capability_report(self) -> dict[str, Any]:
        """What this environment can actually observe, checked not claimed."""

        report: dict[str, Any] = {}

        report[TEXT] = {"live": True, "provider": "builtin"}
        report[FILE] = {"live": True, "provider": "filesystem"}
        report[CODE] = {"live": True, "provider": "ast"}
        report[SYSTEM] = {"live": True, "provider": "platform"}

        vision_provider = self._providers.get(VISION)
        report[VISION] = {
            "live": vision_provider is not None,
            "provider": getattr(vision_provider, "__name__", "none"),
            "note": (
                "no vision model registered - vision observations will be "
                "OCR-only and marked degraded"
                if vision_provider is None
                else ""
            ),
        }

        voice_provider = self._providers.get(VOICE)
        report[VOICE] = {
            "live": voice_provider is not None,
            "provider": getattr(voice_provider, "__name__", "none"),
            "note": (
                "no speech provider registered - voice observations must be "
                "supplied as transcripts by the caller"
                if voice_provider is None
                else ""
            ),
        }

        return report


observe = ObservationInterface()
