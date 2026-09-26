"""Jarvis BrainV2 package.

BUG FIX: ``core/router.py`` and ``core/jarvis.py`` did
``from brains_v2 import process``, but this ``__init__`` was empty, so both
modules died on import. The canonical brain entry point is
``brains_v2.manager.BrainV2.process``; it is exported here as a module-level
function so the legacy call site keeps working.

The import is deferred so that merely importing ``brains_v2`` does not drag in
the entire manager graph (and its optional third-party dependencies).
"""

from __future__ import annotations

from typing import Any

__all__ = ["process", "get_brain"]

_BRAIN = None


def get_brain() -> Any:
    """Return the process-wide BrainV2 singleton, building it on first use."""
    global _BRAIN
    if _BRAIN is None:
        from brains_v2.manager import BrainV2

        _BRAIN = BrainV2()
    return _BRAIN


def process(command: str) -> Any:
    """Canonical single-command entry point for the brain."""
    return get_brain().process(command)
