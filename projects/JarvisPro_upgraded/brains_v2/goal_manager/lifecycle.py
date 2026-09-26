"""BrainV2 Goal Manager — Lifecycle operations."""

from datetime import datetime
from typing import Optional
from .base import GoalManager, BrainGoal, GoalState

_manager: Optional[GoalManager] = None


def get_goal_manager() -> GoalManager:
    global _manager
    if _manager is None:
        _manager = GoalManager()
    return _manager


def create_goal(title: str, description: str = '', priority: int = 2, **kwargs) -> BrainGoal:
    return get_goal_manager().create_goal(title, description, priority, **kwargs)


def update_goal_state(goal_id: str, state: GoalState) -> bool:
    return get_goal_manager().update_state(goal_id, state)


def advance_goal(goal_id: str) -> bool:
    """Move goal to next logical state."""
    goal = get_goal_manager().get_goal(goal_id)
    if not goal:
        return False
    state_flow = {
        GoalState.PLANNING: GoalState.IN_PROGRESS,
        GoalState.IN_PROGRESS: GoalState.COMPLETED,
        GoalState.WAITING: GoalState.IN_PROGRESS,
    }
    next_state = state_flow.get(goal.state)
    if next_state:
        return get_goal_manager().update_state(goal_id, next_state)
    return False
