"""
Voice output.

Thin wrapper over the shared interruptible engine in ``voice.tts`` so
speech can be cut off mid-sentence (feature 3.15).  The original
``speak(text)`` API is unchanged.
"""

from typing import Optional

from voice.tts import tts


def speak(text, wait: bool = True):
    """Say ``text``.  Blocks until finished unless ``wait`` is False."""
    return tts.speak(text, wait=wait)


def speak_async(text):
    """Start speaking and return immediately."""
    return tts.speak(text, wait=False)


def stop():
    """Interrupt whatever is being said right now."""
    return tts.stop()


def is_speaking() -> bool:
    return tts.is_speaking()


def wait(timeout: Optional[float] = None) -> bool:
    return tts.wait(timeout)


def get_engine():
    """The underlying pyttsx3 engine, or None when unavailable."""
    return tts._engine_or_none()


__all__ = [
    "speak",
    "speak_async",
    "stop",
    "is_speaking",
    "wait",
    "get_engine",
]
