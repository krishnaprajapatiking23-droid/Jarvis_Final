"""
==========================================
JARVIS PRO
Interruption Handler  (feature 3.15)
==========================================

Recognises "stop", "wait", "cancel", "never mind", "shut up" and friends,
and actually stops the assistant instead of only replying with text.

When the existing voice layer is available the handler calls
``Speaker.stop()`` so speech is cut off mid-sentence; it also clears any
pending action so a cancelled request is not resumed later.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, Optional

log = logging.getLogger("jarvis.conversation.interruption")

# phrase -> kind of interruption
INTERRUPTIONS: Dict[str, str] = {
    "stop": "stop",
    "stop it": "stop",
    "stop talking": "stop",
    "be quiet": "stop",
    "quiet": "stop",
    "shut up": "stop",
    "enough": "stop",
    "that's enough": "stop",
    "thats enough": "stop",
    "wait": "pause",
    "hold on": "pause",
    "hold up": "pause",
    "one second": "pause",
    "one moment": "pause",
    "just a minute": "pause",
    "pause": "pause",
    "cancel": "cancel",
    "cancel that": "cancel",
    "never mind": "cancel",
    "nevermind": "cancel",
    "forget it": "cancel",
    "forget that": "cancel",
    "abort": "cancel",
    "ruk jao": "stop",
    "continue": "continue",
    "carry on": "continue",
    "keep going": "continue",
    "go on": "continue",
    "resume": "continue",
    "bas": "stop",
}

ACKNOWLEDGEMENTS: Dict[str, str] = {
    "stop": "Stopped.",
    "pause": "Sure, I'll wait.",
    "cancel": "Cancelled.",
    "continue": "Sure - carrying on from where I stopped.",
}

# "continue from where you stopped", "pick up where you left off".
CONTINUE_PREFIXES = (
    "continue",
    "carry on",
    "keep going",
    "resume",
    "pick up where",
)

# "hey jarvis, stop" and "wait jarvis" must still register.
WAKE_WORD = re.compile(r"^(?:hey |ok |okay )?jarvis[,\s]+|[,\s]+jarvis$")


class InterruptionHandler:
    """Detects and executes conversation interruptions."""

    def __init__(self) -> None:
        self.paused = False

    # ------------------------------------------------------------------
    def detect(self, text: str) -> Dict[str, Any]:
        """Return ``{"interrupt": bool, "kind": str, "phrase": str}``."""
        report: Dict[str, Any] = {
            "interrupt": False,
            "interrupted": False,
            "kind": "",
            "phrase": "",
        }
        if not text:
            return report

        lowered = text.strip().lower().rstrip(".!?")
        # "wait jarvis" / "jarvis, stop" are the same request as "stop".
        lowered = WAKE_WORD.sub("", lowered).strip()
        if not lowered:
            return report

        def found(kind: str, phrase: str) -> Dict[str, Any]:
            report.update(
                interrupt=True, interrupted=True, kind=kind, phrase=phrase
            )
            return report

        # Exact match keeps "stop the music" out of the interruption path.
        kind = INTERRUPTIONS.get(lowered)
        if kind:
            return found(kind, lowered)

        # "continue from where you stopped", "keep going", "carry on".
        for prefix in CONTINUE_PREFIXES:
            if lowered.startswith(prefix):
                return found("continue", prefix)

        # Short leading interruptions: "wait, I meant Edge".
        head = lowered.split(",")[0].strip()
        kind = INTERRUPTIONS.get(head)
        if kind and len(head.split()) <= 2:
            return found(kind, head)

        return report

    # ------------------------------------------------------------------
    def silence_voice(self) -> bool:
        """Ask the existing voice layer to stop speaking. True on success."""
        for module_path, attribute in (
            ("brains_v2.voice.speaker", "speaker"),
            ("brains_v2.voice_v2.speaker", "speaker"),
            ("voice.speaker", "speaker"),
        ):
            try:  # pragma: no cover - depends on host audio stack
                module = __import__(module_path, fromlist=[attribute])
                target = getattr(module, attribute, None)
                if target is None:
                    speaker_class = getattr(module, "Speaker", None)
                    target = speaker_class() if speaker_class else None
                stop = getattr(target, "stop", None)
                if callable(stop):
                    stop()
                    return True
            except Exception as error:
                log.debug("speaker stop via %s failed: %s", module_path, error)
        return False

    # ------------------------------------------------------------------
    def handle(self, kind: str, state: Optional[Any] = None) -> str:
        """Execute the interruption and return the acknowledgement."""
        self.silence_voice()

        if kind == "pause":
            self.paused = True
        else:
            self.paused = False

        if kind == "continue":
            self.resume()

        if kind in ("cancel", "stop") and state is not None:
            try:
                state.clear_pending()
            except Exception as error:  # pragma: no cover - defensive
                log.debug("could not clear pending action: %s", error)

        return ACKNOWLEDGEMENTS.get(kind, "Stopped.")

    def resume(self) -> None:
        self.paused = False


interruption_handler = InterruptionHandler()

__all__ = ["InterruptionHandler", "interruption_handler", "INTERRUPTIONS"]
