"""
BrainV2 Goal Manager — Manages goal state within BrainV2 planning pipeline.

Coordinates with the main GoalsManager for cross-manager goal tracking.
"""

import sys as _sys
from typing import Any, Dict, Optional

# Import the canonical GoalsManager (at module level so import errors surface early)
_canonical_available = False
_goals_mgr: Any = None

try:
    from jarvis_core.goals import GoalsManager as _JMGoalsManager
    _canonical_available = True
except ImportError:
    try:
        from goals.manager import GoalsManager as _JMGoalsManager
        _canonical_available = True
    except ImportError:
        _JMGoalsManager = None


class _BrainV2GoalCompat:
    """
    BrainV2-facing goal manager that wraps the canonical GoalsManager.

    Provides the `start(command)`, `update(progress)`, `current()` API
    that brains_v2/manager.py expects, backed by the real GoalsManager
    when available (so goals survive restarts and appear in the main goals
    system), and a lightweight in-memory fallback when it is not.
    """

    def __init__(self):
        self._mgr: Optional[Any] = None
        self._current_goal_id: Optional[str] = None
        self._in_memory: Dict[str, Any] = {}  # id → goal dict (fallback)
        self._in_memory_goals: list = []       # ordered list of goals
        self._use_fallback = not _canonical_available
        if not self._use_fallback:
            try:
                self._mgr = _JMGoalsManager()
            except Exception:
                self._use_fallback = True

    @property
    def _gm(self) -> Optional[Any]:
        """Lazy-init the canonical manager."""
        if self._use_fallback or self._mgr is None:
            return None
        return self._mgr

    # ── API that brains_v2/manager.py calls ──────────────────────────────────

    def start(self, command: str) -> None:
        """
        Begin tracking a goal for `command`.

        Backed by GoalsManager.create_goal() when available so the goal
        persists in the main goals system.
        """
        if self._gm:
            try:
                goal = self._gm.create_goal(title=command[:120], description=command)
                self._current_goal_id = goal.id
                return
            except Exception:
                pass
        # Fallback: lightweight in-memory goal
        import uuid
        import datetime
        gid = str(uuid.uuid4())
        goal = {
            "id": gid,
            "title": command[:120],
            "description": command,
            "state": "active",
            "progress": 0.0,
            "created_at": datetime.datetime.now().isoformat(),
        }
        self._in_memory[gid] = goal
        self._in_memory_goals.append(goal)
        self._current_goal_id = gid

    def update(self, progress: float) -> None:
        """
        Update the current goal's progress.

        100 = completed, 25 = partial failure, etc.
        """
        if not self._current_goal_id:
            return
        if self._gm:
            try:
                goal = self._gm.get_goal(self._current_goal_id)
                if goal:
                    self._gm.update_goal(self._current_goal_id, progress=progress)
                    if progress >= 100:
                        self._gm.complete_goal(self._current_goal_id)
                    self._current_goal_id = None
                    return
            except Exception:
                pass
        # Fallback
        goal = self._in_memory.get(self._current_goal_id)
        if goal:
            goal["progress"] = progress
            if progress >= 100:
                goal["state"] = "completed"
            self._current_goal_id = None

    def current(self) -> Dict[str, Any]:
        """
        Return the current goal's state dict for the BrainV2 status snapshot.

        Returns an empty dict when no goal is active.
        """
        if not self._current_goal_id:
            return {}
        if self._gm:
            try:
                goal = self._gm.get_goal(self._current_goal_id)
                if goal:
                    return {
                        "id": goal.id,
                        "title": goal.title,
                        "progress": goal.progress,
                        "status": goal.status.value if hasattr(goal.status, "value") else str(goal.status),
                    }
            except Exception:
                pass
        # Fallback
        goal = self._in_memory.get(self._current_goal_id, {})
        return dict(goal) if goal else {}

    def get_active_goals(self):
        """Delegate to GoalsManager when available."""
        if self._gm:
            try:
                return self._gm.get_active_goals()
            except Exception:
                pass
        return [g for g in self._in_memory_goals if g.get("state") == "active"]


# ── Singleton ────────────────────────────────────────────────────────────────

goal_manager: _BrainV2GoalCompat = _BrainV2GoalCompat()

__all__ = [
    'BrainGoal', 'GoalState', 'GoalManager',
    'create_goal', 'update_goal_state', 'advance_goal',
    'goal_manager',          # ← the singleton brains_v2/manager.py imports
]
