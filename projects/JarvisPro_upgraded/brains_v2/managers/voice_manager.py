"""Voice manager (roadmap section 29).

Thin, dependency-tolerant facade over whichever speech stack is installed. It
reports honestly when no microphone or TTS engine is present instead of
failing at import time -- the previous three voice packages all raised
OSError: PortAudio library not found simply on import.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from brains_v2.managers.base import BaseManager, ManagerResult

__all__ = ["VoiceManager", "voice_manager"]

log = logging.getLogger("jarvis.voice")


class VoiceManager(BaseManager):
    capability = "voice"
    description = "Speech input and output, when a backend is installed."

    def __init__(self) -> None:
        self._speaker = None
        self._listener = None
        self._speaker_error = ""
        self._listener_error = ""

    # -- lazy backends -----------------------------------------------
    def speaker(self) -> Optional[Any]:
        if self._speaker is not None or self._speaker_error:
            return self._speaker
        for module, attribute in (("voice.speak", "speak"),
                                  ("voice.tts", "speak"),
                                  ("brains_v2.voice.speaker", "speak")):
            try:
                imported = __import__(module, fromlist=[attribute])
                handler = getattr(imported, attribute, None)
                if callable(handler):
                    self._speaker = handler
                    return self._speaker
            except Exception as error:
                self._speaker_error = "%s: %s" % (type(error).__name__, error)
        self._speaker_error = self._speaker_error or "no TTS backend found"
        return None

    def listener(self) -> Optional[Any]:
        if self._listener is not None or self._listener_error:
            return self._listener
        for module, attribute in (("voice.recognizer", "listen"),
                                  ("voice.listener", "listen"),
                                  ("brains_v2.voice.listener", "listen")):
            try:
                imported = __import__(module, fromlist=[attribute])
                handler = getattr(imported, attribute, None)
                if callable(handler):
                    self._listener = handler
                    return self._listener
            except Exception as error:
                self._listener_error = "%s: %s" % (type(error).__name__, error)
        self._listener_error = self._listener_error or "no microphone backend found"
        return None

    # -- operations --------------------------------------------------
    def speak(self, text: str) -> Dict[str, Any]:
        handler = self.speaker()
        if handler is None:
            return ManagerResult(False, "Speech output is unavailable (%s)."
                                 % self._speaker_error, text=text)
        try:
            handler(text)
        except Exception as error:
            return ManagerResult(False, "Speech output failed: %s" % error)
        return ManagerResult(True, text, spoken=True)

    def listen(self, timeout: float = 8.0) -> Dict[str, Any]:
        handler = self.listener()
        if handler is None:
            return ManagerResult(False, "Speech input is unavailable (%s)."
                                 % self._listener_error)
        try:
            heard = handler()
        except Exception as error:
            return ManagerResult(False, "Speech input failed: %s" % error)
        if not heard:
            return ManagerResult(False, "I didn't catch that.")
        return ManagerResult(True, str(heard), heard=str(heard))

    def available(self) -> Dict[str, bool]:
        return {"speak": self.speaker() is not None,
                "listen": self.listener() is not None}

    def can_handle(self, command: Any) -> bool:
        return False  # voice is a surface, not a command route

    def health(self) -> Dict[str, Any]:
        state = self.available()
        detail = "tts=%s stt=%s" % (state["speak"], state["listen"])
        if not state["speak"]:
            detail += " (%s)" % self._speaker_error
        return {"available": any(state.values()),
                "capability": self.capability, "detail": detail}


voice_manager = VoiceManager()
