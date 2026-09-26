"""Goal data models for the Goals Manager."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Optional, Dict, Any


class GoalStatus(Enum):
    ACTIVE = 'active'
    COMPLETED = 'completed'
    PAUSED = 'paused'
    ABANDONED = 'abandoned'
    OVERDUE = 'overdue'


class Priority(Enum):
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


class GoalCategory(Enum):
    WORK = 'work'
    PERSONAL = 'personal'
    LEARNING = 'learning'
    HEALTH = 'health'
    PROJECT = 'project'
    DAILY = 'daily'
    LONG_TERM = 'long_term'
    CAREER = 'career'
    FINANCIAL = 'financial'
    CREATIVE = 'creative'


@dataclass
class Milestone:
    id: str
    title: str
    completed: bool = False
    completed_at: Optional[datetime] = None
    deadline: Optional[datetime] = None
    notes: str = ''
    task_id: Optional[str] = None   # linked task (set by GoalsManager.add_milestone_with_task)


@dataclass
class Goal:
    id: str
    title: str
    description: str = ''
    status: GoalStatus = GoalStatus.ACTIVE
    priority: Priority = Priority.MEDIUM
    category: GoalCategory = GoalCategory.PERSONAL
    created_at: datetime = field(default_factory=datetime.now)
    deadline: Optional[datetime] = None
    progress: float = 0.0  # 0.0 to 1.0
    milestones: List[Milestone] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    parent_goal_id: Optional[str] = None
    task_ids: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def is_overdue(self) -> bool:
        if self.deadline and self.status == GoalStatus.ACTIVE:
            return datetime.now() > self.deadline
        return False

    def mark_complete(self):
        self.status = GoalStatus.COMPLETED
        self.progress = 1.0

    def update_progress(self, value: float):
        self.progress = max(0.0, min(1.0, value))
        if self.progress >= 1.0:
            self.mark_complete()

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'title': self.title,
            'description': self.description,
            'status': self.status.value,
            'priority': self.priority.name,
            'category': self.category.value,
            'progress': self.progress,
            'deadline': self.deadline.isoformat() if self.deadline else None,
            'milestones': [
                {
                    'id': m.id, 'title': m.title, 'completed': m.completed,
                    'completed_at': m.completed_at.isoformat() if m.completed_at else None,
                    'deadline': m.deadline.isoformat() if m.deadline else None,
                    'notes': m.notes,
                    'task_id': m.task_id,
                }
                for m in self.milestones
            ],
            'tags': self.tags,
            'task_ids': self.task_ids,
            'metadata': self.metadata,
            'created_at': self.created_at.isoformat(),
        }
