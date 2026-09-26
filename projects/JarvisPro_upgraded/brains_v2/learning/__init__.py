"""
BrainV2 Learning — Experience-based learning and self-improvement.

Provides:
- Experience extraction and storage
- Pattern detection from command history
- Learning from success/failure
- Strategy adjustment
- Knowledge graph updates
"""

import collections
import threading
from typing import Any, Dict, List, Optional

from .engine import LearningEngine, get_learning_engine
from .experience import Experience, ExperienceType, ExperienceStore
from .patterns import PatternDetector, Pattern, PatternType

__all__ = [
    'LearningEngine', 'get_learning_engine',
    'Experience', 'ExperienceType', 'ExperienceStore',
    'PatternDetector', 'Pattern', 'PatternType',
    'learning',
]


# ---------------------------------------------------------------------------
# Compatibility shim: wraps jarvis_core.learning and adds methods expected by
# brains_v2.manager (learn, favourite_app, favourite_command).  This avoids
# breaking the module-level import in manager.py while keeping all actual
# experience data in the canonical jarvis_core store.
# ---------------------------------------------------------------------------

class _LearningCompat:
    """Adds manager-facing methods over jarvis_core's LearningEngine."""

    def __init__(self) -> None:
        # Defer the heavy import so standalone imports of this module still work.
        self._core = None
        self._cmd_history: List[str] = []
        self._app_history: List[str] = []
        self._lock = threading.Lock()

    @property
    def _engine(self) -> Any:
        if self._core is None:
            from jarvis_core.learning import learning as core_learning
            self._core = core_learning
        return self._core

    # ----- manager.py calls -----

    def learn(self, command: str) -> Optional[str]:
        """Record a raw command as a learning experience."""
        if not command or not isinstance(command, str):
            return None
        with self._lock:
            self._cmd_history.append(command.strip())
        try:
            return self._engine.learn_command(
                command=command,
                resolved_to="",
                success=True,
            ).get("id")
        except Exception:
            return None

    def favourite_app(self) -> str:
        """Return the most-seen application name in command history, or ''."""
        if not self._app_history:
            return ""
        counter: Dict[str, int] = collections.Counter(self._app_history)
        if not counter:
            return ""
        return counter.most_common(1)[0][0]

    def favourite_command(self) -> str:
        """Return the most-seen command class in command history, or ''."""
        if not self._cmd_history:
            return ""
        # Top-level word is a reasonable proxy for "command class".
        tokens: List[str] = []
        for cmd in self._cmd_history:
            first = cmd.strip().split()[0] if cmd.strip() else ""
            if first:
                tokens.append(first.lower())
        if not tokens:
            return ""
        counter: Dict[str, int] = collections.Counter(tokens)
        return counter.most_common(1)[0][0]

    # ----- delegate everything else to the canonical engine -----
    def __getattr__(self, name: str) -> Any:
        return getattr(self._engine, name)


learning = _LearningCompat()
