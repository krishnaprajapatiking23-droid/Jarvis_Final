"""
==========================================
JARVIS PRO
Vision providers
==========================================

Roadmap sections 6 (provider architecture), 36 (failure handling) and
54 (vision health check).

Every way of getting pixels or meaning out of pixels is a provider with the
same shape: it can say whether it is available, describe what it can do, run
inference, and clean up. A provider that is missing reports *why* rather than
raising, so an unavailable camera degrades one capability instead of taking
the process down (section 9: never crash Jarvis because OCR is unavailable).

Two design points worth stating, because they are what stop this being
decoration:

* :class:`VisionResult` is the only return type. A failure carries a machine-
  readable ``error_type`` and a ``recoverable`` flag, so a caller can branch on
  the failure instead of parsing a message.
* Availability is *probed*, not declared. :meth:`Provider.health` actually
  imports the dependency and calls it where cheap, which is why the health
  report can distinguish "not configured" from "installed but broken".
"""

from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable

log = logging.getLogger(__name__)

# Structured error codes (section 36).
UNAVAILABLE = "VISION_PROVIDER_UNAVAILABLE"
INVALID_INPUT = "VISION_INVALID_INPUT"
TIMEOUT = "VISION_TIMEOUT"
INFERENCE_FAILED = "VISION_INFERENCE_FAILED"
PERMISSION_DENIED = "VISION_PERMISSION_DENIED"
NO_DISPLAY = "VISION_NO_DISPLAY"
NO_DEVICE = "VISION_NO_DEVICE"
DEGRADED = "VISION_DEGRADED"

# Health states (section 54).
AVAILABLE = "available"
NOT_AVAILABLE = "unavailable"
DEGRADED_STATE = "degraded"
NOT_CONFIGURED = "not configured"
ERROR = "error"

DEFAULT_TIMEOUT = 20.0


@dataclass
class VisionResult:
    """The single return type for every vision operation."""

    success: bool
    data: Any = None
    error_type: str = ""
    message: str = ""
    recoverable: bool = True
    provider: str = ""
    duration: float = 0.0
    confidence: float = 0.0
    degraded: bool = False
    limitations: list[str] = field(default_factory=list)
    trace_id: str = ""

    def __bool__(self) -> bool:
        return self.success

    @classmethod
    def ok(
        cls,
        data: Any,
        provider: str = "",
        confidence: float = 1.0,
        duration: float = 0.0,
        degraded: bool = False,
        limitations: list[str] | None = None,
    ) -> "VisionResult":
        return cls(
            success=True,
            data=data,
            provider=provider,
            confidence=confidence,
            duration=duration,
            degraded=degraded,
            limitations=list(limitations or []),
        )

    @classmethod
    def fail(
        cls,
        error_type: str,
        message: str,
        provider: str = "",
        recoverable: bool = True,
        duration: float = 0.0,
    ) -> "VisionResult":
        return cls(
            success=False,
            error_type=error_type,
            message=str(message),
            provider=provider,
            recoverable=recoverable,
            duration=duration,
        )

    def report(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "error_type": self.error_type,
            "message": self.message,
            "recoverable": self.recoverable,
            "provider": self.provider,
            "duration": round(float(self.duration), 4),
            "confidence": round(float(self.confidence), 4),
            "degraded": self.degraded,
            "limitations": list(self.limitations),
            "trace_id": self.trace_id,
        }


class Provider:
    """Base class. Subclasses implement ``_probe`` and their own inference."""

    name = "provider"
    capability = "UNKNOWN"
    requires: tuple[str, ...] = ()

    def __init__(self) -> None:
        self._checked = False
        self._available = False
        self._reason = ""
        self._detail: dict[str, Any] = {}
        self._lock = threading.RLock()

    # ------------------------------------------------------------ probing

    def _probe(self) -> tuple[bool, str, dict[str, Any]]:
        """Actually test the dependency. Returns (available, reason, detail)."""

        missing = []

        for module in self.requires:
            try:
                __import__(module)

            except Exception:
                missing.append(module)

        if missing:
            return False, f"missing dependencies: {', '.join(missing)}", {
                "missing": missing
            }

        return True, "", {}

    @property
    def available(self) -> bool:
        with self._lock:
            if not self._checked:
                self._checked = True

                try:
                    self._available, self._reason, self._detail = self._probe()

                except Exception as exc:
                    self._available = False
                    self._reason = f"probe raised {type(exc).__name__}: {exc}"
                    self._detail = {}

            return self._available

    def recheck(self) -> bool:
        """Re-probe. A camera can be plugged in after startup."""

        with self._lock:
            self._checked = False

        return self.available

    def describe(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "capability": self.capability,
            "requires": list(self.requires),
        }

    def health(self) -> dict[str, Any]:
        """Section 54: one honest line about what this provider can do now."""

        ok = self.available

        return {
            "capability": self.capability,
            "provider": self.name,
            "state": AVAILABLE if ok else (
                NOT_CONFIGURED if "missing dependencies" in self._reason else NOT_AVAILABLE
            ),
            "reason": self._reason,
            "detail": dict(self._detail),
        }

    def close(self) -> None:
        """Release resources. Safe to call when never opened."""

        return None

    # ------------------------------------------------------------ running

    def guard(
        self,
        operation: Callable[[], Any],
        timeout: float = DEFAULT_TIMEOUT,
        confidence: float = 1.0,
    ) -> VisionResult:
        """Run an operation with timing, timeout and structured failure.

        The timeout is enforced by running the work on a worker thread and
        abandoning it if it overruns. That reports honestly rather than
        hanging, though it cannot kill a stuck C extension - a limitation
        stated here rather than papered over.
        """

        if not self.available:
            return VisionResult.fail(
                UNAVAILABLE,
                self._reason or f"{self.name} is not available",
                provider=self.name,
                recoverable=True,
            )

        started = time.monotonic()
        box: dict[str, Any] = {}

        def run() -> None:
            try:
                box["value"] = operation()

            except Exception as exc:
                box["error"] = exc

        worker = threading.Thread(target=run, daemon=True)
        worker.start()
        worker.join(timeout)
        elapsed = time.monotonic() - started

        if worker.is_alive():
            return VisionResult.fail(
                TIMEOUT,
                f"{self.name} exceeded {timeout:.1f}s and was abandoned",
                provider=self.name,
                recoverable=True,
                duration=elapsed,
            )

        if "error" in box:
            exc = box["error"]

            return VisionResult.fail(
                INFERENCE_FAILED,
                f"{type(exc).__name__}: {exc}",
                provider=self.name,
                recoverable=True,
                duration=elapsed,
            )

        return VisionResult.ok(
            box.get("value"),
            provider=self.name,
            confidence=confidence,
            duration=elapsed,
        )


# --------------------------------------------------------------------------
# Screenshot


class ScreenshotProvider(Provider):
    """Screen capture. Tries mss, then pyautogui, then PIL's ImageGrab."""

    name = "screenshot"
    capability = "SCREEN_CAPTURE"

    def __init__(self) -> None:
        super().__init__()
        self._backend = ""

    def _probe(self) -> tuple[bool, str, dict[str, Any]]:
        # A headless host has no screen to capture at all, which is a different
        # failure from a missing library and must be reported as such.
        if os.name != "nt" and not os.environ.get("DISPLAY") and not os.environ.get(
            "WAYLAND_DISPLAY"
        ):
            return False, "no display server (headless host)", {
                "headless": True, "error_type": NO_DISPLAY
            }

        for module, backend in (("mss", "mss"), ("pyautogui", "pyautogui")):
            try:
                __import__(module)
                self._backend = backend

                return True, "", {"backend": backend}

            except Exception:
                continue

        try:
            from PIL import ImageGrab  # noqa: F401

            self._backend = "PIL.ImageGrab"

            return True, "", {"backend": "PIL.ImageGrab"}

        except Exception:
            pass

        return False, "no screenshot backend (tried mss, pyautogui, PIL.ImageGrab)", {}

    def capture(self, region: tuple[int, int, int, int] | None = None) -> VisionResult:
        """Capture the screen or a region, returning a Pillow image."""

        def grab():
            if self._backend == "mss":
                import mss
                from PIL import Image

                with mss.mss() as screen:
                    target = screen.monitors[1] if region is None else {
                        "left": region[0], "top": region[1],
                        "width": region[2], "height": region[3],
                    }
                    shot = screen.grab(target)

                    return Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")

            if self._backend == "pyautogui":
                import pyautogui

                return pyautogui.screenshot(region=region)

            from PIL import ImageGrab

            box = None if region is None else (
                region[0], region[1], region[0] + region[2], region[1] + region[3]
            )

            return ImageGrab.grab(bbox=box)

        return self.guard(grab, timeout=15.0)

    def health(self) -> dict[str, Any]:
        report = super().health()

        if self._detail.get("headless"):
            report["state"] = NOT_AVAILABLE
            report["error_type"] = NO_DISPLAY

        report["backend"] = self._backend

        return report


class StaticImageProvider(ScreenshotProvider):
    """A screenshot provider backed by files on disk.

    This is what makes the pipeline testable without a display: the whole
    downstream chain runs unmodified against a rendered image. It is a test
    double by intent, and :meth:`health` says so, so it can never be mistaken
    for live capture.
    """

    name = "static-image"

    def __init__(self, images: list[Any] | None = None) -> None:
        super().__init__()
        self._images = list(images or [])
        self._index = 0

    def _probe(self) -> tuple[bool, str, dict[str, Any]]:
        try:
            from PIL import Image  # noqa: F401

        except Exception:
            return False, "Pillow unavailable", {}

        if not self._images:
            return False, "no images supplied to the static provider", {}

        return True, "", {"images": len(self._images), "simulated": True}

    def push(self, image: Any) -> "StaticImageProvider":
        self._images.append(image)
        self._checked = False

        return self

    def capture(self, region: tuple[int, int, int, int] | None = None) -> VisionResult:
        def grab():
            from PIL import Image

            if not self._images:
                raise RuntimeError("no images remaining")

            item = self._images[min(self._index, len(self._images) - 1)]
            self._index = min(self._index + 1, len(self._images))
            image = Image.open(item) if isinstance(item, (str, bytes)) else item

            if region:
                image = image.crop(
                    (region[0], region[1], region[0] + region[2], region[1] + region[3])
                )

            return image.convert("RGB")

        result = self.guard(grab, timeout=10.0)

        if result.success:
            result.degraded = True
            result.limitations.append(
                "simulated capture from a file, not a live screen"
            )

        return result

    def reset(self) -> None:
        self._index = 0

    def health(self) -> dict[str, Any]:
        report = super().health()
        report["simulated"] = True
        report["note"] = "test double - not live screen capture"

        return report


# --------------------------------------------------------------------------
# Camera


class CameraProvider(Provider):
    """Webcam access through OpenCV, with real open/close lifecycle."""

    name = "camera"
    capability = "CAMERA"
    requires = ("cv2",)

    def __init__(self, index: int = 0) -> None:
        super().__init__()
        self.index = int(index)
        self._capture: Any = None
        self._opened = False

    def _probe(self) -> tuple[bool, str, dict[str, Any]]:
        ok, reason, detail = super()._probe()

        if not ok:
            return ok, reason, detail

        # A device node must exist. Probing by opening the camera would be
        # slow and would fight with whatever else holds it, so the cheap
        # filesystem check comes first on Linux.
        if os.name == "posix":
            devices = [p for p in os.listdir("/dev") if p.startswith("video")]

            if not devices:
                return False, "no camera device found (/dev/video*)", {
                    "devices": [], "error_type": NO_DEVICE
                }

            return True, "", {"devices": sorted(devices)}

        return True, "", {}

    def discover(self, limit: int = 4) -> list[int]:
        """Indices that actually open. Empty list when there is no camera."""

        if not self.available:
            return []

        found: list[int] = []

        try:
            import cv2

            for index in range(limit):
                handle = cv2.VideoCapture(index)

                try:
                    if handle.isOpened():
                        found.append(index)

                finally:
                    handle.release()

        except Exception as exc:
            log.info("camera discovery failed: %s", exc)

        return found

    def open(self, width: int = 0, height: int = 0, fps: int = 0) -> VisionResult:
        if self._opened:
            return VisionResult.ok(
                {"index": self.index, "already_open": True}, provider=self.name
            )

        def start():
            import cv2

            handle = cv2.VideoCapture(self.index)

            if not handle.isOpened():
                handle.release()

                # An index that exists but will not open is usually held by
                # another process - a distinct, recoverable condition.
                raise RuntimeError(
                    f"camera {self.index} could not be opened "
                    f"(absent, or in use by another application)"
                )

            if width and height:
                handle.set(cv2.CAP_PROP_FRAME_WIDTH, int(width))
                handle.set(cv2.CAP_PROP_FRAME_HEIGHT, int(height))

            if fps:
                handle.set(cv2.CAP_PROP_FPS, int(fps))

            self._capture = handle
            self._opened = True

            return {
                "index": self.index,
                "width": int(handle.get(cv2.CAP_PROP_FRAME_WIDTH)),
                "height": int(handle.get(cv2.CAP_PROP_FRAME_HEIGHT)),
                "fps": float(handle.get(cv2.CAP_PROP_FPS)),
            }

        return self.guard(start, timeout=10.0)

    def frame(self) -> VisionResult:
        if not self._opened:
            opened = self.open()

            if not opened.success:
                return opened

        def read():
            from PIL import Image

            ok, raw = self._capture.read()

            if not ok or raw is None:
                raise RuntimeError("frame capture returned no data")

            return Image.fromarray(raw[:, :, ::-1])

        result = self.guard(read, timeout=10.0)

        if not result.success:
            # A failed read usually means the device vanished. Drop the handle
            # so the next call re-opens rather than reusing a dead one.
            self.close()

        return result

    def frames(self, count: int, interval: float = 0.0) -> list[VisionResult]:
        out: list[VisionResult] = []

        for index in range(max(0, int(count))):
            out.append(self.frame())

            if interval and index < count - 1:
                time.sleep(interval)

        return out

    def close(self) -> None:
        if self._capture is not None:
            try:
                self._capture.release()

            except Exception:
                pass

        self._capture = None
        self._opened = False

    @property
    def opened(self) -> bool:
        return self._opened

    def health(self) -> dict[str, Any]:
        report = super().health()
        report["opened"] = self._opened
        report["index"] = self.index

        if self._detail.get("error_type"):
            report["error_type"] = self._detail["error_type"]

        return report


class MockCamera(CameraProvider):
    """A camera backed by supplied frames, for testing the pipeline.

    Declares itself simulated in :meth:`health` so a passing pipeline test can
    never be reported as live camera support (section 62).
    """

    name = "mock-camera"

    def __init__(self, frames: list[Any] | None = None, fail_after: int = -1) -> None:
        super().__init__(index=-1)
        self._frames = list(frames or [])
        self._position = 0
        self._fail_after = int(fail_after)
        self._busy = False

    def set_busy(self, busy: bool) -> None:
        """Simulate the device being held by another application."""

        self._busy = bool(busy)

    def _probe(self) -> tuple[bool, str, dict[str, Any]]:
        if not self._frames:
            return False, "mock camera has no frames", {"error_type": NO_DEVICE}

        return True, "", {"frames": len(self._frames), "simulated": True}

    def discover(self, limit: int = 4) -> list[int]:
        return [-1] if self.available else []

    def open(self, width: int = 0, height: int = 0, fps: int = 0) -> VisionResult:
        if self._busy:
            return VisionResult.fail(
                UNAVAILABLE,
                "camera is in use by another application",
                provider=self.name,
                recoverable=True,
            )

        if not self.available:
            return VisionResult.fail(
                NO_DEVICE, self._reason, provider=self.name, recoverable=False
            )

        self._opened = True

        return VisionResult.ok({"index": -1, "simulated": True}, provider=self.name)

    def frame(self) -> VisionResult:
        if not self._opened:
            opened = self.open()

            if not opened.success:
                return opened

        if 0 <= self._fail_after <= self._position:
            self.close()

            return VisionResult.fail(
                INFERENCE_FAILED,
                "frame capture returned no data (simulated disconnect)",
                provider=self.name,
                recoverable=True,
            )

        frame = self._frames[self._position % len(self._frames)]
        self._position += 1

        result = VisionResult.ok(frame, provider=self.name)
        result.degraded = True
        result.limitations.append("simulated frame, not live camera hardware")

        return result

    def close(self) -> None:
        self._opened = False

    def health(self) -> dict[str, Any]:
        report = super().health()
        report["simulated"] = True
        report["note"] = "test double - not live camera hardware"

        return report


# --------------------------------------------------------------------------
# Vision-language model


class VisionModelProvider(Provider):
    """Multimodal image understanding through the project's model router.

    Section 10 forbids presenting OCR as image understanding. This provider is
    the only thing entitled to claim understanding, and when it is unavailable
    the caller is told to fall back explicitly rather than silently.
    """

    name = "vision-model"
    capability = "IMAGE_UNDERSTANDING"

    def __init__(self, model: str = "") -> None:
        super().__init__()
        self.model = model
        self._router: Any = None

    def _probe(self) -> tuple[bool, str, dict[str, Any]]:
        try:
            from core.model_router import router

        except Exception as exc:
            return False, f"model router unavailable: {type(exc).__name__}", {}

        self._router = router

        try:
            info = router.health()

        except Exception as exc:
            return False, f"router health check failed: {type(exc).__name__}", {}

        models = info.get("models") or []

        # A router with models is not a vision model. Only a model that
        # declares the vision capability can serve this provider at all.
        capable = [
            m for m in models
            if "vision" in (m.get("capabilities") or [])
        ]

        if not capable:
            return False, (
                "no model declares the 'vision' capability - image "
                "understanding is unavailable, only OCR"
            ), {"models": len(models)}

        # A model's own "available" flag is optimistic: the router reports
        # configured models as available with runs=0 and success_rate=1.0
        # before anything has ever reached them. Treating that as proof of
        # reachability claimed working multimodal vision on a host with no
        # model runtime at all, which section 62 forbids. Reachability is
        # only established by a successful run.
        proven = [
            m for m in capable
            if int(m.get("runs", 0)) > 0 and float(m.get("success_rate", 0)) > 0
        ]

        names = [m.get("model", "?") for m in capable]

        if not proven:
            return False, (
                f"vision model {names[0]} is configured but has never answered "
                f"successfully - no local runtime or network reachable"
            ), {
                "configured": names,
                "proven": [],
                "error_type": NOT_CONFIGURED,
                "configured_but_unverified": True,
            }

        if not self.model:
            self.model = str(proven[0].get("model", ""))

        return True, "", {
            "configured": names,
            "proven": [m.get("model") for m in proven],
        }

    def describe_image(self, image: Any, prompt: str = "") -> VisionResult:
        question = prompt or "Describe what is visible in this image."

        def run():
            # router.ask takes (prompt, capability, options) - an earlier
            # version of this call passed image=/model= keyword arguments that
            # the router does not accept, so it would have raised TypeError
            # the first time a vision model became reachable.
            reply = self._router.ask(
                question,
                capability="vision",
                options={"image": image, "model": self.model or None},
            )

            if isinstance(reply, dict):
                if not reply.get("ok", True):
                    raise RuntimeError(
                        reply.get("error") or "vision model returned no answer"
                    )

                return {
                    "description": reply.get("text", ""),
                    "model": reply.get("model", self.model),
                    "provider": reply.get("provider", ""),
                    "latency": reply.get("latency", 0.0),
                }

            return {"description": str(reply), "model": self.model}

        return self.guard(run, timeout=60.0, confidence=0.8)

    def health(self) -> dict[str, Any]:
        report = super().health()

        if self._detail.get("configured_but_unverified"):
            report["state"] = NOT_CONFIGURED
            report["configured"] = self._detail.get("configured", [])
            report["note"] = (
                "a vision-capable model is configured but has never been "
                "reached; image understanding falls back to OCR and reports "
                "itself as degraded"
            )

        return report


def probe_all(providers: list[Provider]) -> dict[str, Any]:
    """Health across a set of providers (section 54)."""

    rows = [p.health() for p in providers]

    return {
        "providers": rows,
        "available": [r["capability"] for r in rows if r["state"] == AVAILABLE],
        "unavailable": [
            {"capability": r["capability"], "reason": r["reason"]}
            for r in rows
            if r["state"] != AVAILABLE
        ],
        "checked_at": time.time(),
    }
