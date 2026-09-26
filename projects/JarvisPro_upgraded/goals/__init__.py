"""
Goals Manager — Hierarchical goal creation, tracking, and management.

Provides goal lifecycle management for JarvisPro, supporting:
- Short-term and long-term goals
- Goal → Task decomposition
- Progress tracking and milestones
- Deadline management
- Goal reminders
"""

from .manager import GoalsManager, get_goals_manager
from .models import Goal, GoalStatus, Priority, GoalCategory

__all__ = [
    'GoalsManager', 'get_goals_manager',
    'Goal', 'GoalStatus', 'Priority', 'GoalCategory',
]
