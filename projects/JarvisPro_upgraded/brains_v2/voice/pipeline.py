"""Voice/text conversation pipeline (BUG 8 + Phase 5).

Rewritten from the minified one-line version into normal, readable Python:
one logical statement per line, type hints and docstrings on the public
methods, and explicit state transitions.

BUG 8: ``input()`` is wrapped so ``EOFError`` (Ctrl+D, piped stdin,
headless runs) and ``KeyboardInterrupt`` both lead to a clean shutdown with
no traceback and no lingering threads.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Callable, Dict, List, Optional

from brains_v2.runtime import brain_call

__all__ = [
    "VoicePipeline",
    "pipeline",
    "EXIT_PHRASES",
    "WAKE_PHRASES",
    "WAKE_PATTERN",
    "TEXT_PROMPT",
    "NO_BRAIN_MESSAGE",
]

log = logging.getLogger(__name__)

EXIT_PHRASES = ("exit", "quit", "bye", "goodbye", "stop listening", "shut down")
WAKE_PHRASES = ("jarvis", "hey jarvis", "ok jarvis")

# Raw string: the previous version used '\b' inside a normal string, which is
# a backspace character rather than a word boundary.
WAKE_PATTERN = re.compile(
    r"\b(?:" + "|".join(re.escape(phrase) for phrase in WAKE_PHRASES) + r")\b",
    re.IGNORECASE,
)

TEXT_PROMPT = "\nYou > "
NO_BRAIN_MESSAGE = "I am not fully started yet - no brain is attached."


class VoicePipeline:
    """Drives one conversation loop over voice or text input."""

    def __init__(
        self,
        voice_enabled: bool = True,
        brain: Any = None,
        handler: Optional[Callable[[str], Any]] = None,
        reader: Optional[Callable[[str], str]] = None,
    ) -> None:
        self.voice_enabled = bool(voice_enabled)
        self.brain = brain
        self.handler = handler
        self._reader: Callable[[str], str] = reader or self._default_reader
        self.running = False
        self.turns = 0
        self.stopped_by_eof = False
        self.stopped_by_interrupt = False
        self.stop_reason = ""
        self._listener: Any = None
        self._speaker: Any = None
        self.greeting_shown = False
        self.dropped_turns = 0

    # ------------------------------------------------------------------ input
    @staticmethod
    def _default_reader(prompt: str) -> str:
        """Read one line from stdin. Kept separate so tests can inject one."""
        return input(prompt)

    def _read_turn(self, prompt: str = TEXT_PROMPT) -> Optional[str]:
        """Read one user turn. Returns ``None`` to request shutdown."""
        try:
            text = self._reader(prompt)
        except EOFError:
            self.stopped_by_eof = True
            log.info("input stream closed (EOF); shutting down")
            return None
        except KeyboardInterrupt:
            self.stopped_by_interrupt = True
            log.info("interrupted by user; shutting down")
            return None
        except Exception as error:
            log.warning("input failed: %r", error)
            return None
        return text.strip()

    def _listen(self) -> Optional[str]:
        """Capture one spoken turn, falling back to text on any failure."""
        if not self.voice_enabled:
            return self._read_turn()
        if self._listener is None:
            try:
                from brains_v2.voice.listener import listener

                self._listener = listener
            except Exception as error:
                log.info("voice input unavailable (%s); using text", error)
                self.voice_enabled = False
                return self._read_turn()
        try:
            heard = self._listener.listen()
        except KeyboardInterrupt:
            self.stopped_by_interrupt = True
            return None
        except Exception as error:
            log.warning("microphone error: %r; falling back to text", error)
            self.voice_enabled = False
            return self._read_turn()
        if not heard:
            self.dropped_turns += 1
            return None
        if self.brain is None:
            self.dropped_turns += 1
            log.error("no brain attached; turn dropped")
            return NO_BRAIN_MESSAGE
        return str(heard).strip()

    # ----------------------------------------------------------------- output
    def _say(self, text: str) -> None:
        """Speak if a speaker is usable, otherwise print."""
        message = str(text or "").strip()
        if not message:
            return
        print(f"Jarvis > {message}")
        if not self.voice_enabled:
            return
        if self._speaker is None:
            try:
                from brains_v2.voice.speaker import speaker

                self._speaker = speaker
            except Exception as error:
                log.info("text to speech unavailable (%s); replies printed", error)
                return
        try:
            self._speaker.say(message)
        except Exception as error:
            log.warning("speech output failed: %r", error)

    # ------------------------------------------------------------- processing
    def _reply_text(self, result: Any) -> str:
        """Normalise whatever the brain returned into speakable text."""
        if result is None:
            return ""
        if isinstance(result, str):
            return result
        if isinstance(result, dict):
            for key in ("reply", "text", "message", "response", "answer"):
                value = result.get(key)
                if isinstance(value, str) and value.strip():
                    return value
            log.debug("result had no speakable text (keys=%s)", list(result))
            return ""
        return str(result)

    def _handle(self, text: str) -> Any:
        """Route one turn through the handler or brain.

        The raw result is returned unchanged; the speaking layer normalises
        it with :meth:`_reply_text`, so no caller indexes ``result["reply"]``
        and a dict without a text key can never raise.
        """
        self.turns += 1
        try:
            if self.handler is not None:
                return self.handler(text)
            if self.brain is not None:
                return brain_call(self.brain, text)
        except Exception as error:
            log.exception("turn failed")
            return f"Sorry, that failed: {type(error).__name__}."
        return ""

    def attach_brain(self, brain: Any) -> Any:
        """Inject the real brain instance (BUG 1 dependency injection)."""
        if brain is None:
            raise ValueError("attach_brain() needs a brain instance")
        self.brain = brain
        return brain

    def has_brain(self) -> bool:
        return self.brain is not None

    def announce(self, message: str = "Jarvis is online.", printed: bool = False) -> str:
        """BUG 3: say/show the startup state so Jarvis never looks frozen."""
        self.greeting_shown = True
        if printed:
            print(message)
        try:
            self._say(message)
        except Exception as error:  # speaking must never block startup
            log.warning("could not speak the greeting: %s", error)
        return message

    @staticmethod
    def is_exit(text: str) -> bool:
        """True when the user asked to end the session."""
        return str(text or "").strip().lower() in EXIT_PHRASES

    @staticmethod
    def has_wake_word(text: str) -> bool:
        """True when the wake word appears as a whole word."""
        return bool(WAKE_PATTERN.search(str(text or "")))

    # ------------------------------------------------------------- lifecycle
    def shutdown(self, reason: str = "requested") -> Dict[str, Any]:
        """Stop the loop and release voice resources exactly once."""
        self.running = False
        self.stop_reason = reason
        for name in ("_listener", "_speaker"):
            component = getattr(self, name, None)
            if component is None:
                continue
            closer = getattr(component, "stop", None) or getattr(
                component, "close", None
            )
            if closer is None:
                continue
            try:
                closer()
            except Exception as error:
                log.debug("%s cleanup failed: %r", name, error)
        log.info("pipeline stopped (%s) after %d turns", reason, self.turns)
        return self.report()

    def report(self) -> Dict[str, Any]:
        """Machine-readable session outcome."""
        return {
            "turns": self.turns,
            "reason": self.stop_reason,
            "eof": self.stopped_by_eof,
            "interrupted": self.stopped_by_interrupt,
            "running": self.running,
            "has_brain": self.has_brain(),
            "dropped_turns": self.dropped_turns,
            "greeting_shown": self.greeting_shown,
        }

    def run(self, mode: str = "text") -> Dict[str, Any]:
        """Run the conversation loop until EOF, interrupt or an exit phrase."""
        self.running = True
        self.stopped_by_eof = False
        self.stopped_by_interrupt = False
        self.stop_reason = ""
        use_voice = mode == "voice" and self.voice_enabled

        while self.running:
            text = self._listen() if use_voice else self._read_turn()

            if text is None:
                if self.stopped_by_eof:
                    return self.shutdown("eof")
                if self.stopped_by_interrupt:
                    return self.shutdown("interrupted")
                return self.shutdown("input-unavailable")

            if not text:
                continue

            if self.is_exit(text):
                self._say("Goodbye.")
                return self.shutdown("exit-phrase")

            reply = self._handle(text)
            spoken = self._reply_text(reply)
            if spoken:
                self._say(spoken)

        return self.shutdown(self.stop_reason or "stopped")


pipeline = VoicePipeline(voice_enabled=False)
