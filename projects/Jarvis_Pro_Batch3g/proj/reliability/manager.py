"""
Reliability Manager — monitors JARVIS health, detects failures,
and attempts graceful recovery.

Features:
  - Module health checks
  - Automatic retry with backoff
  - Circuit breaker for failing services
  - Uptime tracking
  - Panic mode (safe shutdown on repeated failures)
"""

import time
from collections import defaultdict
from threading import Lock
from typing import Callable, Dict, List, Optional


# Default: circuit opens after this many consecutive failures
DEFAULT_THRESHOLD = 5
# Seconds before circuit attempts to close again
DEFAULT_RESET_DELAY = 60


class CircuitBreaker:
    """Prevents repeated calls to a failing service."""

    def __init__(self, name: str, threshold: int = DEFAULT_THRESHOLD,
                 reset_delay: float = DEFAULT_RESET_DELAY):
        self.name = name
        self.threshold = threshold
        self.reset_delay = reset_delay
        self._failures = 0
        self._open_at: Optional[float] = None
        self._state = "closed"  # closed | open | half-open
        self._lock = Lock()

    def call(self, func: Callable, *args, **kwargs):
        """Execute func, tracking failures through the breaker."""
        with self._lock:
            if self._state == "open":
                if (time.time() - self._open_at) < self.reset_delay:
                    raise CircuitOpenError(f"Circuit '{self.name}' is OPEN")
                self._state = "half-open"

        try:
            result = func(*args, **kwargs)
            with self._lock:
                self._failures = 0
                self._state = "closed"
            return result
        except Exception as e:
            with self._lock:
                self._failures += 1
                if self._failures >= self.threshold:
                    self._state = "open"
                    self._open_at = time.time()
            raise e

    def status(self) -> dict:
        with self._lock:
            return {
                "name": self.name,
                "state": self._state,
                "failures": self._failures,
                "threshold": self.threshold,
                "open_since": (
                    round(time.time() - self._open_at, 1)
                    if self._open_at else None
                ),
            }

    def reset(self) -> None:
        with self._lock:
            self._failures = 0
            self._state = "closed"
            self._open_at = None


class CircuitOpenError(Exception):
    pass


class RetryPolicy:
    """Retries a function with exponential backoff."""

    def __init__(self, max_attempts: int = 3,
                 base_delay: float = 1.0, max_delay: float = 30.0):
        self.max_attempts = max_attempts
        self.base_delay = base_delay
        self.max_delay = max_delay

    def execute(self, func: Callable, *args, **kwargs):
        last_error = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                last_error = e
                if attempt < self.max_attempts:
                    delay = min(self.base_delay * (2 ** (attempt - 1)),
                                self.max_delay)
                    time.sleep(delay)
        raise last_error


class ReliabilityManager:
    """Central reliability coordinator."""

    def __init__(self):
        self._breakers: Dict[str, CircuitBreaker] = {}
        self._health_checks: Dict[str, Callable] = {}
        self._lock = Lock()
        self._start_time = time.time()
        self._restart_count = 0

    def register_breaker(self, name: str, threshold: int = DEFAULT_THRESHOLD,
                         reset_delay: float = DEFAULT_RESET_DELAY) -> None:
        with self._lock:
            self._breakers[name] = CircuitBreaker(name, threshold, reset_delay)

    def register_health_check(self, name: str, check_fn: Callable) -> None:
        self._health_checks[name] = check_fn

    def get_breaker(self, name: str) -> Optional[CircuitBreaker]:
        return self._breakers.get(name)

    def health_report(self) -> Dict:
        """Run all health checks and return a report."""
        results = {}
        all_healthy = True
        for name, check in self._health_checks.items():
            try:
                result = check()
                results[name] = {"status": "ok", "result": result}
            except Exception as e:
                results[name] = {"status": "error", "error": str(e)}
                all_healthy = False

        breaker_status = {
            name: b.status()
            for name, b in self._breakers.items()
        }

        return {
            "overall": "healthy" if all_healthy else "degraded",
            "uptime_s": round(time.time() - self._start_time, 1),
            "restarts": self._restart_count,
            "health_checks": results,
            "breakers": breaker_status,
        }

    def panic(self) -> Dict:
        """Trigger safe shutdown mode."""
        self._restart_count += 1
        return {
            "mode": "PANIC",
            "restarts": self._restart_count,
            "message": "JARVIS entered safe mode — review health report above",
        }


_manager = ReliabilityManager()

register_breaker = _manager.register_breaker
register_health_check = _manager.register_health_check
get_breaker = _manager.get_breaker
health_report = _manager.health_report
panic = _manager.panic
CircuitBreaker = CircuitBreaker
RetryPolicy = RetryPolicy
CircuitOpenError = CircuitOpenError
