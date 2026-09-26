"""Availability state machine for LLM providers (Phase 4 / 14).

Previously every user command re-attempted ``ollama serve`` and printed
several diagnostic lines. The state machine caches the failure, applies
exponential backoff with a cooldown, and only allows an explicit retry
(:meth:`retry_now`) or an expired cooldown to try again.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable, Dict

__all__ = ["ProviderState", "ProviderStateMachine"]

log = logging.getLogger(__name__)


class ProviderState:
    """Discrete provider states."""

    UNKNOWN = "UNKNOWN"
    STARTING = "STARTING"
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"
    COOLDOWN = "COOLDOWN"
    FAILED = "FAILED"

    ALL = (UNKNOWN, STARTING, AVAILABLE, UNAVAILABLE, COOLDOWN, FAILED)


class ProviderStateMachine:
    """Thread-safe availability tracker with bounded retries."""

    def __init__(
        self,
        base_cooldown: float = 30.0,
        max_cooldown: float = 600.0,
        max_attempts: int = 5,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.base_cooldown = float(base_cooldown)
        self.max_cooldown = float(max_cooldown)
        self.max_attempts = int(max_attempts)
        self._clock = clock
        self._lock = threading.RLock()
        self.state = ProviderState.UNKNOWN
        self.failures = 0
        self.last_error = ""
        self._retry_at = 0.0

    # --------------------------------------------------------------- queries
    def cooldown_remaining(self) -> float:
        with self._lock:
            return max(0.0, self._retry_at - self._clock())

    def cooling_down(self) -> bool:
        with self._lock:
            if self.state == ProviderState.FAILED:
                return True
            return self.cooldown_remaining() > 0

    def should_attempt_start(self) -> bool:
        """True when spawning/reconnecting is allowed right now."""
        with self._lock:
            if self.state in (ProviderState.AVAILABLE, ProviderState.STARTING):
                return False
            if self.state == ProviderState.FAILED:
                return False
            return self.cooldown_remaining() <= 0

    def report(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "state": self.state,
                "failures": self.failures,
                "last_error": self.last_error,
                "cooldown_remaining": round(self.cooldown_remaining(), 2),
                "may_start": self.should_attempt_start(),
            }

    # ----------------------------------------------------------- transitions
    def mark_starting(self) -> None:
        with self._lock:
            self.state = ProviderState.STARTING

    def mark_available(self) -> None:
        with self._lock:
            self.state = ProviderState.AVAILABLE
            self.failures = 0
            self.last_error = ""
            self._retry_at = 0.0

    def mark_launched(self) -> None:
        """Spawned but not yet confirmed listening: arm a short cooldown."""
        with self._lock:
            self.state = ProviderState.COOLDOWN
            self._retry_at = self._clock() + min(self.base_cooldown, 30.0)

    def mark_unavailable(self, error: str = "") -> None:
        """Provider cannot be used at all (e.g. package not installed)."""
        with self._lock:
            self.state = ProviderState.UNAVAILABLE
            if error:
                self.last_error = error
            self._retry_at = self._clock() + self.base_cooldown

    def mark_failed(self, error: str = "") -> float:
        """Record a failure and return the cooldown in seconds."""
        with self._lock:
            self.failures += 1
            if error:
                self.last_error = error
            delay = min(
                self.base_cooldown * (2 ** (self.failures - 1)), self.max_cooldown
            )
            if self.failures >= self.max_attempts:
                self.state = ProviderState.FAILED
                log.warning(
                    "provider marked FAILED after %d attempts: %s",
                    self.failures,
                    self.last_error,
                )
            else:
                self.state = ProviderState.COOLDOWN
            self._retry_at = self._clock() + delay
            return delay

    def reset(self) -> None:
        """Explicit operator retry: clear failures and cooldown."""
        with self._lock:
            self.state = ProviderState.UNKNOWN
            self.failures = 0
            self.last_error = ""
            self._retry_at = 0.0

    # Alias used by callers/tests that phrase it as an explicit retry.
    retry_now = reset
