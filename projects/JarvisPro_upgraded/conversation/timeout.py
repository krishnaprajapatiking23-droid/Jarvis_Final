"""Conversation timeouts (roadmap section 3: Context Expiration)."""

from __future__ import annotations

import time
from typing import Any, Dict, Optional

__all__ = ["ConversationTimeout", "conversation_timeout"]

IDLE_SECONDS = 15 * 60          # topic goes stale
SESSION_SECONDS = 2 * 60 * 60   # session ends


class ConversationTimeout:
    """Decides when context is too old to keep using."""

    def __init__(self, idle: float = IDLE_SECONDS,
                 session: float = SESSION_SECONDS):
        self.idle = idle
        self.session = session
        self._last_turn: Optional[float] = None
        self._started: Optional[float] = None

    def touch(self, now: Optional[float] = None) -> None:
        now = now if now is not None else time.time()
        if self._started is None:
            self._started = now
        self._last_turn = now

    def idle_seconds(self, now: Optional[float] = None) -> float:
        if self._last_turn is None:
            return 0.0
        now = now if now is not None else time.time()
        return max(0.0, now - self._last_turn)

    def session_seconds(self, now: Optional[float] = None) -> float:
        if self._started is None:
            return 0.0
        now = now if now is not None else time.time()
        return max(0.0, now - self._started)

    def context_expired(self, now: Optional[float] = None) -> bool:
        return self.idle_seconds(now) > self.idle

    def session_expired(self, now: Optional[float] = None) -> bool:
        return self.session_seconds(now) > self.session

    def reset(self) -> None:
        self._last_turn = None
        self._started = None

    def state(self, now: Optional[float] = None) -> Dict[str, Any]:
        return {
            "idle_seconds": round(self.idle_seconds(now), 1),
            "session_seconds": round(self.session_seconds(now), 1),
            "context_expired": self.context_expired(now),
            "session_expired": self.session_expired(now),
        }


conversation_timeout = ConversationTimeout()
