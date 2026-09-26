"""
Speaker Engine

Wraps the shared interruptible engine (``voice.tts``) so that
``speaker.stop()`` really cuts speech off mid-sentence instead of only
taking effect after the current sentence has finished (feature 3.15).
"""

from typing import Optional

from voice.tts import DEFAULT_RATE, InterruptibleTTS, tts


class Speaker:
    """Voice output for the brains_v2 pipeline."""

    def __init__(self, rate: int = DEFAULT_RATE, shared: bool = True) -> None:
        # pyttsx3 misbehaves with several live engines, so every Speaker
        # shares one by default.
        self.engine = tts if shared else InterruptibleTTS(rate=rate)
        if rate != self.engine.rate:
            self.engine.set_rate(rate)

    # ------------------------------------------------------------------
    def speak(self, text, wait: bool = True):
        """Say ``text``.  Blocks until finished unless ``wait`` is False."""
        return self.engine.speak(text, wait=wait)

    def speak_async(self, text):
        """Start speaking and return immediately."""
        return self.engine.speak(text, wait=False)

    def stop(self):
        """Interrupt the current utterance and drop anything queued."""
        return self.engine.stop()

    def is_speaking(self) -> bool:
        return self.engine.is_speaking()

    def wait(self, timeout: Optional[float] = None) -> bool:
        return self.engine.wait(timeout)

    @property
    def available(self) -> bool:
        return self.engine.available


speaker = Speaker()

__all__ = ["Speaker", "speaker"]
