"""Wake-word detection (v2 surface).

Adapter over :mod:`brains_v2.speech.wakeword`, which holds the single
implementation.
"""

from __future__ import annotations

from brains_v2.speech.wakeword import WakeWord, detect, wake_word

__all__ = ["WakeWord", "wake_word", "detect"]
