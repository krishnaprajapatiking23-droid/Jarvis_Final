"""Goals Manager — Core goal management logic."""

import json
import uuid
import logging
from pathlib import Path
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional, Dict, Any

from .models import Goal, GoalStatus, Priority, GoalCategory, Milestone

if TYPE_CHECKING:
    from jarvis_core.tasks import TaskManager

logger = logging.getLogger(__name__)


class GoalsManager:
    """Manages goal lifecycle: create, track, decompose, remind."""

    def __init__(self, data_dir: Optional[str] = None, task_manager: Optional["TaskManager"] = None):
        if data_dir is None:
            data_dir = str(Path('data/goals').expanduser())
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.goals_file = self.data_dir / 'goals.json'
        self._goals: Dict[str, Goal] = {}
        self._task_manager: Optional["TaskManager"] = task_manager
        self._load_goals()

    def _load_goals(self):
        if self.goals_file.exists():
            try:
                with open(self.goals_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                for g in data.get('goals', []):
                    milestones = []
                    for m in g.get('milestones', []):
                        milestones.append(Milestone(
                            id=m['id'], title=m['title'],
                            completed=m.get('completed', False),
                            completed_at=datetime.fromisoformat(m['completed_at'])
                            if m.get('completed_at') else None,
                            deadline=datetime.fromisoformat(m['deadline'])
                            if m.get('deadline') else None,
                            notes=m.get('notes', ''),
                            task_id=m.get('task_id'),
                        ))
                    goal = Goal(
                        id=g['id'], title=g['title'], description=g.get('description', ''),
                        status=GoalStatus(g.get('status', 'active')),
                        priority=Priority[g.get('priority', 'MEDIUM')],
                        category=GoalCategory(g.get('category', 'personal')),
                        progress=g.get('progress', 0.0),
                        milestones=milestones,
                        tags=g.get('tags', []),
                        task_ids=g.get('task_ids', []),
                        metadata=g.get('metadata', {}),
                    )
                    if g.get('deadline'):
                        goal.deadline = datetime.fromisoformat(g['deadline'])
                    if g.get('created_at'):
                        goal.created_at = datetime.fromisoformat(g['created_at'])
                    self._goals[goal.id] = goal
            except Exception as e:
                logger.error(f'Failed to load goals: {e}')

    def _save_goals(self):
        try:
            data = {'goals': [g.to_dict() for g in self._goals.values()]}
            with open(self.goals_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, default=str)
        except Exception as e:
            logger.error(f'Failed to save goals: {e}')

    def create_goal(
        self, title: str, description: str = '', priority: Priority = Priority.MEDIUM,
        category: GoalCategory = GoalCategory.PERSONAL, deadline: Optional[datetime] = None,
        tags: Optional[List[str]] = None, parent_goal_id: Optional[str] = None,
    ) -> Goal:
        """Create a new goal."""
        goal = Goal(
            id=str(uuid.uuid4()), title=title, description=description,
            priority=priority, category=category, deadline=deadline,
            tags=tags or [], parent_goal_id=parent_goal_id,
        )
        self._goals[goal.id] = goal
        self._save_goals()
        return goal

    def get_goal(self, goal_id: str) -> Optional[Goal]:
        return self._goals.get(goal_id)

    def get_all_goals(self, status: Optional[GoalStatus] = None) -> List[Goal]:
        goals = list(self._goals.values())
        if status:
            goals = [g for g in goals if g.status == status]
        return sorted(goals, key=lambda g: (-g.priority.value, g.created_at))

    def get_active_goals(self) -> List[Goal]:
        return self.get_all_goals(GoalStatus.ACTIVE)

    def update_goal(self, goal_id: str, **kwargs) -> Optional[Goal]:
        goal = self._goals.get(goal_id)
        if not goal:
            return None
        for key, value in kwargs.items():
            if hasattr(goal, key) and key not in ('id',):
                setattr(goal, key, value)
        self._save_goals()
        return goal

    def delete_goal(self, goal_id: str) -> bool:
        if goal_id in self._goals:
            del self._goals[goal_id]
            self._save_goals()
            return True
        return False

    def complete_goal(self, goal_id: str) -> bool:
        goal = self._goals.get(goal_id)
        if not goal:
            return False
        goal.mark_complete()
        self._save_goals()
        return True

    def add_milestone(self, goal_id: str, title: str, deadline: Optional[datetime] = None) -> Optional[Milestone]:
        goal = self._goals.get(goal_id)
        if not goal:
            return None
        milestone = Milestone(id=str(uuid.uuid4()), title=title, deadline=deadline)
        goal.milestones.append(milestone)
        self._save_goals()
        return milestone

    def complete_milestone(self, goal_id: str, milestone_id: str) -> bool:
        goal = self._goals.get(goal_id)
        if not goal:
            return False
        for m in goal.milestones:
            if m.id == milestone_id:
                m.completed = True
                m.completed_at = datetime.now()
                # Auto-update progress based on milestones
                if goal.milestones:
                    completed = sum(1 for mm in goal.milestones if mm.completed)
                    goal.progress = completed / len(goal.milestones)
                self._save_goals()
                return True
        return False

    def link_task(self, goal_id: str, task_id: str) -> bool:
        goal = self._goals.get(goal_id)
        if not goal:
            return False
        if task_id not in goal.task_ids:
            goal.task_ids.append(task_id)
            self._save_goals()
        return True

    def set_task_manager(self, task_manager: "TaskManager") -> None:
        """Inject the TaskManager for auto-task creation from milestones."""
        self._task_manager = task_manager

    def add_milestone_with_task(
        self, goal_id: str, title: str, deadline: Optional[datetime] = None,
        manager: Optional[str] = None
    ) -> Optional[Milestone]:
        """Add milestone AND create a linked TaskManager task automatically."""
        milestone = self.add_milestone(goal_id, title, deadline)
        if milestone and self._task_manager is not None:
            try:
                task = self._task_manager.create(
                    title=f"[Goal] {title}",
                    kind="goal_step",
                    owner="owner",
                    manager=manager or "automation",
                    depends_on=[],
                    payload={"goal_id": goal_id, "milestone_id": milestone.id, "milestone_title": title},
                )
                self.link_task(goal_id, task.task_id)
                milestone.task_id = task.task_id
                self._save_goals()
                logger.info("Auto-created task %s for milestone %s (goal %s)",
                            task.task_id, milestone.id, goal_id)
            except Exception as e:
                logger.warning("Failed to auto-create task for milestone %s: %s", milestone.id, e)
        return milestone

    def get_overdue_goals(self) -> List[Goal]:
        return [g for g in self._goals.values() if g.is_overdue()]

    def get_goals_by_category(self, category: GoalCategory) -> List[Goal]:
        return [g for g in self._goals.values() if g.category == category]

    def search_goals(self, query: str) -> List[Goal]:
        q = query.lower()
        return [
            g for g in self._goals.values()
            if q in g.title.lower() or q in g.description.lower() or q in ' '.join(g.tags).lower()
        ]

    def get_summary(self) -> Dict[str, Any]:
        goals = list(self._goals.values())
        return {
            'total': len(goals),
            'active': sum(1 for g in goals if g.status == GoalStatus.ACTIVE),
            'completed': sum(1 for g in goals if g.status == GoalStatus.COMPLETED),
            'overdue': sum(1 for g in goals if g.is_overdue()),
            'by_category': {
                cat.value: sum(1 for g in goals if g.category == cat)
                for cat in GoalCategory
            }
        }


_manager: Optional[GoalsManager] = None


def get_goals_manager() -> GoalsManager:
    global _manager
    if _manager is None:
        _manager = GoalsManager()
    return _manager
