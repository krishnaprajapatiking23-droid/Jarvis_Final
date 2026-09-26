"""
Microphone Engine

The recogniser and the microphone are created on first use instead of at
import time.  Opening audio hardware while the module was being imported
made the whole ``brains_v2.voice`` package (and anything importing it)
fail on machines without a working microphone or PyAudio.
"""

import logging

log = logging.getLogger("jarvis.voice.microphone")

LANGUAGE = "en-IN"
AMBIENT_NOISE_DURATION = 0.5


class Microphone:
    """Speech input.  Returns "" whenever audio is unavailable."""

    def __init__(self, language=LANGUAGE):
        self.language = language
        self.recognizer = None
        self.microphone = None
        self.available = None

    # ------------------------------------------------------------------
    def _setup(self):
        """Create the recogniser/microphone once.  False when impossible."""
        if self.available is not None:
            return self.available

        try:
            import speech_recognition as sr

            self.recognizer = sr.Recognizer()
            self.microphone = sr.Microphone()
            self.available = True
        except Exception as error:
            log.warning("microphone unavailable: %s", error)
            self.recognizer = None
            self.microphone = None
            self.available = False

        return self.available

    # ------------------------------------------------------------------
    def listen(self):
        """Listen once and return the transcript, or "" on any failure."""
        if not self._setup():
            return ""

        try:
            with self.microphone as source:
                self.recognizer.adjust_for_ambient_noise(
                    source,
                    duration=AMBIENT_NOISE_DURATION,
                )

                print("Listening...")

                audio = self.recognizer.listen(source)
        except Exception as error:
            log.warning("could not record audio: %s", error)
            return ""

        try:
            return self.recognizer.recognize_google(
                audio,
                language=self.language,
            )
        except Exception:
            # Nothing recognisable was said.
            return ""


microphone = Microphone()
