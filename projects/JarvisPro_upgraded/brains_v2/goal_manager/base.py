"""BrainV2 Goal Manager — Base models for goal state in BrainV2."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Optional, Dict, Any
import uuid


class GoalState(Enum):
    CREATED = 'created'
    PLANNING = 'planning'
    IN_PROGRESS = 'in_progress'
    WAITING = 'waiting'
    COMPLETED = 'completed'
    FAILED = 'failed'
    CANCELLED = 'cancelled'


@dataclass
class BrainGoal:
    """Goal representation within BrainV2 execution context."""
    id: str
    title: str
    description: str = ''
    state: GoalState = GoalState.CREATED
    priority: int = 2  # 1-4
    parent_id: Optional[str] = None
    sub_goal_ids: List[str] = field(default_factory=list)
    task_ids: List[str] = field(default_factory=list)
    deadline: Optional[datetime] = None
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    progress: float = 0.0
    attempt: int = 0
    max_attempts: int = 3
    failure_reason: str = ''
    metadata: Dict[str, Any] = field(default_factory=dict)

    def is_leaf(self) -> bool:
        return len(self.sub_goal_ids) == 0

    def can_retry(self) -> bool:
        return self.attempt < self.max_attempts

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id, 'title': self.title, 'description': self.description,
            'state': self.state.value, 'priority': self.priority,
            'parent_id': self.parent_id, 'sub_goal_ids': self.sub_goal_ids,
            'task_ids': self.task_ids, 'progress': self.progress,
            'attempt': self.attempt, 'failure_reason': self.failure_reason,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
        }


class GoalManager:
    """Manages goal lifecycle within BrainV2 pipeline."""

    def __init__(self):
        self._goals: Dict[str, BrainGoal] = {}
        self._goal_stack: List[str] = []  # Active goal hierarchy

    def create_goal(self, title: str, description: str = '', priority: int = 2,
                    parent_id: Optional[str] = None, deadline: Optional[datetime] = None,
                    max_attempts: int = 3) -> BrainGoal:
        goal = BrainGoal(
            id=str(uuid.uuid4()), title=title, description=description,
            priority=priority, parent_id=parent_id, deadline=deadline,
            max_attempts=max_attempts, state=GoalState.PLANNING
        )
        self._goals[goal.id] = goal
        if parent_id and parent_id in self._goals:
            self._goals[parent_id].sub_goal_ids.append(goal.id)
        self._goal_stack.append(goal.id)
        return goal

    def get_goal(self, goal_id: str) -> Optional[BrainGoal]:
        return self._goals.get(goal_id)

    def update_state(self, goal_id: str, state: GoalState) -> bool:
        goal = self._goals.get(goal_id)
        if not goal:
            return False
        goal.state = state
        goal.updated_at = datetime.now()
        return True

    def increment_attempt(self, goal_id: str) -> bool:
        goal = self._goals.get(goal_id)
        if not goal:
            return False
        goal.attempt += 1
        goal.updated_at = datetime.now()
        return True

    def get_active_goals(self) -> List[BrainGoal]:
        return [g for g in self._goals.values() if g.state in (GoalState.PLANNING, GoalState.IN_PROGRESS)]

    def get_root_goals(self) -> List[BrainGoal]:
        return [g for g in self._goals.values() if g.parent_id is None]
