"""
==========================================
JARVIS PRO
Pipeline trace printing (configurable)
==========================================

The brain used to print its whole internal report on every turn, which
buried the actual reply in thousands of characters of dictionaries.  Those
prints are still useful while debugging, so they are kept - but behind a
switch.

Enable them in ``config/settings.json``::

    "pipeline_debug": true

When the flag is off (the default) only the reply is printed.
"""

from __future__ import annotations

import logging

log = logging.getLogger("jarvis.trace")


def enabled() -> bool:
    """True when verbose pipeline printing is switched on."""
    try:
        from conversation.identity import identity

        return bool(identity.settings().get("pipeline_debug", False))
    except Exception as error:  # pragma: no cover - defensive
        log.debug("pipeline_debug flag unreadable: %s", error)
        return False


def trace(*parts) -> None:
    """Print one internal trace line, but only when tracing is enabled."""
    if not enabled():
        return
    try:
        print(*parts)
    except Exception as error:  # pragma: no cover - defensive
        log.debug("trace print failed: %s", error)


__all__ = ["enabled", "trace"]
