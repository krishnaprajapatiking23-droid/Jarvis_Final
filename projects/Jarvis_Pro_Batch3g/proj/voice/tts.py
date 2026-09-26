"""
==========================================
JARVIS PRO
Interruptible Text-To-Speech core  (feature 3.15)
==========================================

``pyttsx3`` speaks synchronously: ``engine.runAndWait()`` blocks the
calling thread until the whole sentence has been read out, so a
``stop()`` request could never arrive while JARVIS was talking.

This module owns ONE engine and drives it from a dedicated worker
thread.  Speech is queued, so:

  * ``speak()`` still blocks by default - existing call sites keep
    working exactly as before
  * ``speak(text, wait=False)`` returns immediately
  * ``stop()`` can be called from any other thread and cuts the current
    utterance off mid-sentence, dropping anything queued behind it

``pyttsx3`` is optional.  On a machine without a working audio stack
(CI, headless test runs) speech degrades to printing the line, so
importing the voice layer never breaks the rest of JARVIS.
"""

from __future__ import annotations

import logging
import queue
import threading
from typing import Optional

log = logging.getLogger("jarvis.voice.tts")

DEFAULT_RATE = 175
DEFAULT_VOLUME = 1.0


class InterruptibleTTS:
    """A pyttsx3 engine that can be stopped while it is speaking."""

    def __init__(
        self,
        rate: int = DEFAULT_RATE,
        volume: float = DEFAULT_VOLUME,
        echo: bool = True,
    ) -> None:
        self.rate = rate
        self.volume = volume
        self.echo = echo
        self.last_spoken = ""
        self.interrupted = False

        self._engine = None
        self._engine_failed = False
        self._lock = threading.RLock()
        self._queue: "queue.Queue[Optional[str]]" = queue.Queue()
        self._worker: Optional[threading.Thread] = None
        self._speaking = threading.Event()
        self._idle = threading.Event()
        self._idle.set()

    # ------------------------------------------------------------------
    # engine
    # ------------------------------------------------------------------
    def _engine_or_none(self):
        """Lazily initialise pyttsx3; ``None`` when speech is unavailable."""
        with self._lock:
            if self._engine is not None or self._engine_failed:
                return self._engine
            try:
                import pyttsx3  # imported lazily: optional dependency

                engine = pyttsx3.init()
                engine.setProperty("rate", self.rate)
                engine.setProperty("volume", self.volume)
                self._engine = engine
            except Exception as error:  # pragma: no cover - host audio stack
                self._engine_failed = True
                log.warning(
                    "text to speech unavailable (%s); replies will be printed",
                    error,
                )
            return self._engine

    @property
    def available(self) -> bool:
        """True when a real voice engine could be initialised."""
        return self._engine_or_none() is not None

    def set_rate(self, rate: int) -> None:
        self.rate = int(rate)
        engine = self._engine_or_none()
        if engine is not None:
            try:
                engine.setProperty("rate", self.rate)
            except Exception as error:  # pragma: no cover - defensive
                log.debug("could not set rate: %s", error)

    # ------------------------------------------------------------------
    # worker
    # ------------------------------------------------------------------
    def _ensure_worker(self) -> None:
        with self._lock:
            if self._worker is not None and self._worker.is_alive():
                return
            self._worker = threading.Thread(
                target=self._run,
                name="jarvis-tts",
                daemon=True,
            )
            self._worker.start()

    def _run(self) -> None:
        while True:
            text = self._queue.get()
            try:
                if text is None:
                    return
                if self.interrupted:
                    continue

                self._speaking.set()
                self._idle.clear()

                engine = self._engine_or_none()
                if engine is None:
                    continue

                try:
                    engine.say(text)
                    engine.runAndWait()
                except Exception as error:  # pragma: no cover - host audio
                    log.warning("speech failed: %s", error)
            finally:
                self._speaking.clear()
                if self._queue.empty():
                    self._idle.set()
                self._queue.task_done()

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------
    def speak(self, text: str, wait: bool = True, timeout: Optional[float] = None) -> str:
        """Say ``text``.  Blocks until finished unless ``wait`` is False."""
        message = (text or "").strip()
        if not message:
            return ""

        self.last_spoken = message
        self.interrupted = False

        if self.echo:
            print(f"Jarvis: {message}")

        self._idle.clear()
        self._ensure_worker()
        self._queue.put(message)

        if wait:
            self.wait(timeout)
        return message

    def stop(self) -> bool:
        """Interrupt the current utterance and drop the queue.

        Safe to call from another thread, and safe to call when nothing
        is being said.
        """
        self.interrupted = True

        while True:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break
            else:
                self._queue.task_done()

        engine = self._engine
        if engine is not None:
            try:
                engine.stop()
            except Exception as error:  # pragma: no cover - host audio stack
                log.debug("engine stop failed: %s", error)

        self._speaking.clear()
        self._idle.set()
        return True

    def is_speaking(self) -> bool:
        return self._speaking.is_set()

    def wait(self, timeout: Optional[float] = None) -> bool:
        """Block until the queue has drained.  True when idle."""
        return self._idle.wait(timeout)


# Shared engine: pyttsx3 does not cope with several live instances.
tts = InterruptibleTTS()


def speak(text: str, wait: bool = True) -> str:
    return tts.speak(text, wait=wait)


def stop() -> bool:
    return tts.stop()


def is_speaking() -> bool:
    return tts.is_speaking()


def wait(timeout: Optional[float] = None) -> bool:
    return tts.wait(timeout)


__all__ = [
    "InterruptibleTTS",
    "tts",
    "speak",
    "stop",
    "is_speaking",
    "wait",
]
