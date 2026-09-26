"""Graceful shutdown (roadmap section 27: Safe Startup / Recovery).

Runs registered cleanup hooks in reverse registration order, bounded by a
timeout, so one slow hook cannot hang the exit.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable, Dict, List, Tuple

__all__ = ["register", "unregister", "shutdown", "hooks"]

log = logging.getLogger("jarvis.shutdown")

_HOOKS: List[Tuple[str, Callable[[], Any]]] = []
_LOCK = threading.RLock()
DEFAULT_TIMEOUT = 10.0


def register(name: str, hook: Callable[[], Any]) -> None:
    """Add a cleanup hook. Later registrations run first."""
    if not callable(hook):
        raise TypeError("shutdown hook %r is not callable" % name)
    with _LOCK:
        _HOOKS.append((str(name), hook))


def unregister(name: str) -> bool:
    with _LOCK:
        before = len(_HOOKS)
        _HOOKS[:] = [(n, h) for n, h in _HOOKS if n != name]
        return len(_HOOKS) < before


def hooks() -> List[str]:
    with _LOCK:
        return [name for name, _ in _HOOKS]


def shutdown(timeout: float = DEFAULT_TIMEOUT) -> Dict[str, Any]:
    """Run every hook; never raise, always report."""
    started = time.time()
    with _LOCK:
        ordered = list(reversed(_HOOKS))

    done: List[str] = []
    failed: List[Dict[str, str]] = []

    for name, hook in ordered:
        if time.time() - started > timeout:
            failed.append({"hook": name, "error": "skipped: shutdown timed out"})
            continue
        try:
            hook()
            done.append(name)
        except Exception as error:
            log.warning("shutdown hook %s failed: %r", name, error)
            failed.append({"hook": name,
                           "error": "%s: %s" % (type(error).__name__, error)})

    return {
        "success": not failed,
        "completed": done,
        "failed": failed,
        "seconds": round(time.time() - started, 2),
    }
