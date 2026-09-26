"""Jarvis runtime: dependency injection for brain/pipeline + startup report.

Fixes the three deep-repair bugs:

* BUG 1 - the voice pipeline was a module-level singleton built without a
  brain, so commands had nowhere to go. ``JarvisRuntime`` builds one brain and
  injects that exact instance into the pipeline (``attach_brain``).
* BUG 2 - callers used ``brain.handle(text)``. The canonical BrainV2 API is
  ``process(text)``; ``brain_call`` resolves the canonical method and only
  falls back to legacy names for third-party brains.
* BUG 3 - startup was silent. ``start()`` reports every service and announces
  "Jarvis is online." (or the degraded/offline reason).
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

log = logging.getLogger(__name__)

__all__ = [
    "BRAIN_METHODS",
    "GREETING",
    "brain_call",
    "ServiceState",
    "StartupReport",
    "JarvisRuntime",
    "get_runtime",
    "reset_runtime",
]

# ``process`` is the canonical BrainV2 entry point; the rest exist only so a
# custom/legacy brain object still works. This is resolution, not an alias.
BRAIN_METHODS = ("process", "handle", "respond", "__call__")
GREETING = "Jarvis is online."


def brain_call(brain: Any, text: str) -> Any:
    """Send ``text`` to ``brain`` using its canonical public API."""
    if brain is None:
        raise RuntimeError("no brain is attached")
    for name in BRAIN_METHODS:
        method = getattr(brain, name, None)
        if callable(method):
            return method(text)
    raise AttributeError(
        "brain %r exposes none of %s" % (type(brain).__name__, ", ".join(BRAIN_METHODS))
    )


@dataclass
class ServiceState:
    name: str
    status: str = "pending"  # ok | degraded | failed | pending
    detail: str = ""
    critical: bool = False
    duration_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "detail": self.detail,
            "critical": self.critical,
            "duration_ms": round(self.duration_ms, 2),
        }


@dataclass
class StartupReport:
    services: List[ServiceState] = field(default_factory=list)
    greeting: str = ""
    started_at: float = field(default_factory=time.time)

    @property
    def failures(self) -> List[ServiceState]:
        return [item for item in self.services if item.status == "failed"]

    @property
    def degraded(self) -> List[ServiceState]:
        return [item for item in self.services if item.status == "degraded"]

    @property
    def critical_failures(self) -> List[ServiceState]:
        return [item for item in self.failures if item.critical]

    @property
    def online(self) -> bool:
        return not self.critical_failures

    @property
    def status(self) -> str:
        if not self.online:
            return "OFFLINE"
        return "DEGRADED" if (self.degraded or self.failures) else "ONLINE"

    def lines(self) -> List[str]:
        marks = {"ok": "[+]", "degraded": "[~]", "failed": "[!]", "pending": "[ ]"}
        output = []
        for item in self.services:
            line = "%s %s" % (marks.get(item.status, "[ ]"), item.name)
            if item.detail:
                line += " - %s" % item.detail
            output.append(line)
        return output

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "online": self.online,
            "greeting": self.greeting,
            "services": [item.to_dict() for item in self.services],
            "started_at": self.started_at,
        }


class JarvisRuntime:
    """Owns the single brain instance and injects it into the pipeline."""

    def __init__(
        self,
        brain_factory: Optional[Callable[[], Any]] = None,
        pipeline_factory: Optional[Callable[[], Any]] = None,
    ) -> None:
        self._brain_factory = brain_factory
        self._pipeline_factory = pipeline_factory
        self._brain: Any = None
        self._pipeline: Any = None
        self._lock = threading.RLock()
        self._report: Optional[StartupReport] = None
        self._kernel: Any = None

    # ----------------------------------------------------------------- brain
    def _build_brain(self) -> Any:
        if self._brain_factory is not None:
            return self._brain_factory()
        from brains_v2.manager import BrainV2  # imported lazily on purpose

        return BrainV2()

    def brain(self) -> Any:
        with self._lock:
            if self._brain is None:
                self._brain = self._build_brain()
            return self._brain

    # ---------------------------------------------------------------- kernel
    def kernel(self) -> Any:
        """Feature kernel (observability, policy, tasks, decisions, analytics).

        Built lazily and shared, so GUI, voice and Android all observe the same
        traces, permissions and task state.
        """
        with self._lock:
            if self._kernel is None:
                from jarvis_core.kernel import Kernel

                self._kernel = Kernel()
            return self._kernel

    def process(self, text: str) -> Any:
        """Canonical entry point: traced, measured, then handed to the brain."""
        try:
            kernel = self.kernel()
        except Exception as error:  # kernel must never block a reply
            log.warning("kernel unavailable: %s", error)
            return brain_call(self.brain(), text)

        obs = kernel.observability
        trace_id = obs.start_trace(text)
        try:
            with obs.span("input", "text"):
                pass
            with obs.span("manager", "brain"):
                reply = brain_call(self.brain(), text)
            with obs.span("output", "reply"):
                pass
            obs.end_trace(trace_id, "ok")
            kernel.analytics.record("command", text[:60], True, trace_id=trace_id)
            return reply
        except Exception as error:
            obs.end_trace(trace_id, "error")
            kernel.analytics.record("command", text[:60], False, trace_id=trace_id,
                                    meta={"error": f"{type(error).__name__}: {error}"})
            raise

    def last_trace(self) -> Optional[str]:
        try:
            traces = self.kernel().observability.recent_traces(1)
        except Exception:
            return None
        return traces[0]["trace_id"] if traces else None

    # -------------------------------------------------------------- pipeline
    def _build_pipeline(self) -> Any:
        if self._pipeline_factory is not None:
            return self._pipeline_factory()
        from brains_v2.voice.pipeline import pipeline

        return pipeline

    def pipeline(self) -> Any:
        with self._lock:
            if self._pipeline is None:
                built = self._build_pipeline()
                brain = self.brain()
                attach = getattr(built, "attach_brain", None)
                if callable(attach):
                    attach(brain)
                else:  # pragma: no cover - custom pipelines
                    setattr(built, "brain", brain)
                self._pipeline = built
            return self._pipeline

    # --------------------------------------------------------------- startup
    def _step(self, report: StartupReport, name: str, critical: bool, work: Callable[[], Any]) -> Any:
        state = ServiceState(name=name, critical=critical)
        report.services.append(state)
        began = time.time()
        try:
            value = work()
        except Exception as error:
            state.status = "failed" if critical else "degraded"
            state.detail = "%s: %s" % (type(error).__name__, error) if critical else "service unavailable; continuing without it"
            state.duration_ms = (time.time() - began) * 1000.0
            log.warning("startup step %s failed: %s", name, error)
            return None
        state.status = "ok"
        state.duration_ms = (time.time() - began) * 1000.0
        return value

    def start(self, speak: Optional[Callable[[str], Any]] = None, announce: bool = True) -> StartupReport:
        report = StartupReport()

        def storage() -> Any:
            from brains_v2.database import database

            return database

        def scheduler() -> Any:
            from schedular.scheduler import scheduler as service

            return service

        self._step(report, "storage", False, storage)
        self._step(report, "scheduler", False, scheduler)
        self._step(report, "brain", True, self.brain)
        self._step(report, "pipeline", True, self.pipeline)
        self._step(report, "kernel", False, self.kernel)
        self._step(report, "recovery", False, lambda: self.kernel().recover())

        if report.online:
            report.greeting = GREETING
            if report.degraded or report.failures:
                report.greeting = GREETING + " Some services are degraded."
        else:
            names = ", ".join(item.name for item in report.critical_failures)
            report.greeting = "Jarvis could not start: %s unavailable." % names

        if announce:
            for line in report.lines():
                print(line)
            print(report.greeting)
            if speak is not None:
                try:
                    speak(report.greeting)
                except Exception as error:  # speaking must never break startup
                    log.warning("could not speak the greeting: %s", error)
        self._report = report
        return report

    def report(self) -> Optional[StartupReport]:
        return self._report

    def status(self) -> str:
        return self._report.status if self._report else "STOPPED"

    def shutdown(self) -> None:
        with self._lock:
            pipeline = self._pipeline
            if pipeline is not None:
                stop = getattr(pipeline, "shutdown", None)
                if callable(stop):
                    try:
                        stop()
                    except Exception as error:  # pragma: no cover
                        log.warning("pipeline shutdown failed: %s", error)
            self._report = None


_RUNTIME: Optional[JarvisRuntime] = None
_RUNTIME_LOCK = threading.RLock()


def get_runtime() -> JarvisRuntime:
    """Process-wide runtime. Tests and embedders can inject their own."""
    global _RUNTIME
    with _RUNTIME_LOCK:
        if _RUNTIME is None:
            _RUNTIME = JarvisRuntime()
        return _RUNTIME


def reset_runtime(runtime: Optional[JarvisRuntime] = None) -> JarvisRuntime:
    global _RUNTIME
    with _RUNTIME_LOCK:
        _RUNTIME = runtime or JarvisRuntime()
        return _RUNTIME
