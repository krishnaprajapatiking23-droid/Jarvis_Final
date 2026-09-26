"""Core engine facade.

One place the GUI, voice surface and Android server can import to send a
command, without each of them reaching into the brain internals.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

__all__ = ["Engine", "engine", "process", "start", "stop"]

log = logging.getLogger("jarvis.engine")


class Engine:
    """Thin, surface-agnostic wrapper over the Jarvis runtime."""

    def __init__(self) -> None:
        self._runtime = None
        self._report: Dict[str, Any] = {}

    def runtime(self) -> Any:
        if self._runtime is None:
            from brains_v2.runtime import get_runtime

            self._runtime = get_runtime()
        return self._runtime

    def start(self) -> Dict[str, Any]:
        if not self._report:
            self._report = self.runtime().start().to_dict()
        return self._report

    def online(self) -> bool:
        return bool(self.start().get("online"))

    def process(self, text: str) -> Dict[str, Any]:
        """Send one command and always return a dict with a reply."""
        if not str(text or "").strip():
            return {"success": False, "reply": "I didn't get a command."}

        try:
            outcome = self.runtime().process(text)
        except Exception as error:
            log.warning("command failed: %r", error)
            return {"success": False,
                    "reply": "That command failed: %s" % error,
                    "error": "%s: %s" % (type(error).__name__, error)}

        if isinstance(outcome, dict):
            outcome.setdefault("reply", "")
            outcome.setdefault("success", bool(outcome.get("reply")))
            return outcome

        return {"success": True, "reply": str(outcome)}

    def stop(self) -> Dict[str, Any]:
        from core.shutdown import shutdown

        try:
            self.runtime().shutdown()
        except Exception as error:
            log.info("runtime shutdown reported: %s", error)
        return shutdown()

    def health(self) -> Dict[str, Any]:
        return self.start()


engine = Engine()


def process(text: str) -> Dict[str, Any]:
    return engine.process(text)


def start() -> Dict[str, Any]:
    return engine.start()


def stop() -> Dict[str, Any]:
    return engine.stop()
