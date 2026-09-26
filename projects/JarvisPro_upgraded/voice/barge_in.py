"""
==========================================
JARVIS PRO
Voice barge-in monitor  (feature 3.15)
==========================================

Listens WHILE JARVIS is speaking and stops the speech the moment the
user says an interruption phrase ("stop", "wait", "never mind", ...).
The interruption vocabulary is the one owned by
``conversation.interruption``, so text and voice interruptions behave
identically.

Usage from a voice pipeline::

    with barge_in.watch(speaker):
        speaker.speak(reply)

Only an exact interruption phrase stops playback, which keeps JARVIS
from silencing itself when its own reply happens to contain the word
"stop" and keeps normal speech from being cut off by background noise.

Requirements: a microphone and ``speech_recognition``.  When either is
missing the monitor disables itself and interruption falls back to the
next command JARVIS receives - it never raises into the pipeline.
Set ``"barge_in": false`` in ``config/settings.json`` to turn the
feature off.
"""

from __future__ import annotations

import contextlib
import logging
import threading
import time
from typing import Any, Iterator, Optional

from conversation.identity import identity
from conversation.interruption import interruption_handler

log = logging.getLogger("jarvis.voice.barge_in")

# How long to wait for speech to start, and how much of it to capture.
LISTEN_TIMEOUT = 0.6
PHRASE_TIME_LIMIT = 2.0
POLL_INTERVAL = 0.05


class BargeInMonitor:
    """Stops the speaker when the user talks over JARVIS."""

    def __init__(
        self,
        listen_timeout: float = LISTEN_TIMEOUT,
        phrase_time_limit: float = PHRASE_TIME_LIMIT,
    ) -> None:
        self.listen_timeout = listen_timeout
        self.phrase_time_limit = phrase_time_limit

        self.last_phrase = ""
        self.last_kind = ""
        self.interruptions = 0

        self._active = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._unavailable = False

    # ------------------------------------------------------------------
    def enabled(self) -> bool:
        """Configuration-driven switch; False once the mic proved absent."""
        if self._unavailable:
            return False
        setting = identity.settings().get("barge_in", True)
        return bool(setting)

    def matches(self, text: str) -> str:
        """The interruption kind for ``text``, or "" when it is not one."""
        report = interruption_handler.detect(text)
        return str(report.get("kind", "")) if report.get("interrupt") else ""

    # ------------------------------------------------------------------
    def start(self, speaker: Any) -> bool:
        """Begin watching.  True when a monitor thread was started."""
        if not self.enabled():
            return False
        if self._thread is not None and self._thread.is_alive():
            return False

        self._active.set()
        self._thread = threading.Thread(
            target=self._loop,
            args=(speaker,),
            name="jarvis-barge-in",
            daemon=True,
        )
        self._thread.start()
        return True

    def stop(self) -> None:
        """Stop watching.  Never blocks the pipeline for long."""
        self._active.clear()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=0.2)
        self._thread = None

    @contextlib.contextmanager
    def watch(self, speaker: Any) -> Iterator["BargeInMonitor"]:
        """Context manager that watches for barge-in while speaking."""
        started = False
        try:
            started = self.start(speaker)
        except Exception as error:  # pragma: no cover - defensive
            log.debug("barge-in monitor could not start: %s", error)
        try:
            yield self
        finally:
            if started:
                try:
                    self.stop()
                except Exception as error:  # pragma: no cover - defensive
                    log.debug("barge-in monitor could not stop: %s", error)

    # ------------------------------------------------------------------
    def _loop(self, speaker: Any) -> None:  # pragma: no cover - needs a mic
        recogniser, microphone = self._audio()
        if recogniser is None or microphone is None:
            self._unavailable = True
            return

        while self._active.is_set():
            try:
                if not speaker.is_speaking():
                    time.sleep(POLL_INTERVAL)
                    continue
            except Exception:
                return

            text = self._listen_once(recogniser, microphone)
            if not self._active.is_set():
                return
            if not text:
                continue

            kind = self.matches(text)
            if not kind:
                continue

            self.last_phrase = text
            self.last_kind = kind
            self.interruptions += 1
            try:
                speaker.stop()
            except Exception as error:
                log.debug("could not stop the speaker: %s", error)
            return

    # ------------------------------------------------------------------
    def _audio(self):  # pragma: no cover - needs a mic
        try:
            import speech_recognition as sr
        except Exception as error:
            log.info("barge-in disabled: speech_recognition missing (%s)", error)
            return None, None

        try:
            recogniser = sr.Recognizer()
            recogniser.dynamic_energy_threshold = True
            return recogniser, sr.Microphone()
        except Exception as error:
            log.info("barge-in disabled: no microphone (%s)", error)
            return None, None

    def _listen_once(self, recogniser, microphone) -> str:  # pragma: no cover
        try:
            with microphone as source:
                audio = recogniser.listen(
                    source,
                    timeout=self.listen_timeout,
                    phrase_time_limit=self.phrase_time_limit,
                )
        except Exception:
            # Silence, or the mic is busy: just try again.
            return ""

        try:
            return str(recogniser.recognize_google(audio, language="en-IN") or "")
        except Exception:
            return ""


barge_in = BargeInMonitor()

__all__ = ["BargeInMonitor", "barge_in"]
