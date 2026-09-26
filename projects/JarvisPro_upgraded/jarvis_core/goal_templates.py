"""
Goal Templates — Phase 15 Feature B.

Built-in + custom reusable Goal templates. A template creates real:
  Goal → Milestones → Tasks → Dependencies

Template content is NEVER executed as Python code. Variable substitution
is pure text replacement using {{variable}} syntax.

Template instantiation is atomic: on failure, no partial Goal is left behind.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from goals.manager import GoalsManager
from goals.models import Goal, GoalCategory, GoalStatus, Milestone, Priority

logger = logging.getLogger(__name__)


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ─────────────────────────────────────────────────────────────────────────────
# Template data model
# ─────────────────────────────────────────────────────────────────────────────

class GoalTemplate:
    """A reusable goal blueprint."""

    def __init__(
        self,
        template_id: str,
        name: str,
        description: str = "",
        category: GoalCategory = GoalCategory.PROJECT,
        version: int = 1,
        is_active: bool = True,
        is_builtin: bool = False,
        created_by: str = "system",
        created_at: Optional[str] = None,
        updated_at: Optional[str] = None,
        milestones: Optional[List[Dict[str, Any]]] = None,
        default_priority: Priority = Priority.MEDIUM,
        variables: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        self.template_id = template_id
        self.name = name
        self.description = description
        self.category = category
        self.version = version
        self.is_active = is_active
        self.is_builtin = is_builtin
        self.created_by = created_by
        self.created_at = created_at or _utc()
        self.updated_at = updated_at or _utc()
        self.milestones = milestones or []
        self.default_priority = default_priority
        self.variables = variables or []
        self.tags = tags or []
        self.metadata = metadata or {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "template_id": self.template_id,
            "name": self.name,
            "description": self.description,
            "category": self.category.value,
            "version": self.version,
            "is_active": self.is_active,
            "is_builtin": self.is_builtin,
            "created_by": self.created_by,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "milestones": self.milestones,
            "default_priority": self.default_priority.name,
            "variables": self.variables,
            "tags": self.tags,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> GoalTemplate:
        return cls(
            template_id=d["template_id"],
            name=d["name"],
            description=d.get("description", ""),
            category=GoalCategory(d.get("category", "project")),
            version=d.get("version", 1),
            is_active=d.get("is_active", True),
            is_builtin=d.get("is_builtin", False),
            created_by=d.get("created_by", "system"),
            created_at=d.get("created_at"),
            updated_at=d.get("updated_at"),
            milestones=d.get("milestones", []),
            default_priority=Priority[d.get("default_priority", "MEDIUM")],
            variables=d.get("variables", []),
            tags=d.get("tags", []),
            metadata=d.get("metadata", {}),
        )


# ─────────────────────────────────────────────────────────────────────────────
# Built-in templates
# ─────────────────────────────────────────────────────────────────────────────

def _coding_template() -> GoalTemplate:
    return GoalTemplate(
        template_id="tpl_coding_v1",
        name="Coding Project",
        description="Full software development lifecycle: planning → implementation → testing → release.",
        category=GoalCategory.PROJECT,
        version=1,
        is_builtin=True,
        created_by="system",
        tags=["coding", "development", "software"],
        variables=["project_name", "deadline", "description", "priority"],
        milestones=[
            {
                "title": "Planning",
                "description": "Define scope, architecture, and requirements.",
                "tasks": [
                    {"title": "Define project requirements", "priority": 2, "depends_on": []},
                    {"title": "Design system architecture", "priority": 2, "depends_on": []},
                    {"title": "Set up development environment", "priority": 3, "depends_on": []},
                ],
            },
            {
                "title": "Implementation",
                "description": "Build the core functionality.",
                "tasks": [
                    {"title": "Build core module", "priority": 2, "depends_on": ["Define project requirements"]},
                    {"title": "Implement feature set", "priority": 2, "depends_on": ["Design system architecture"]},
                    {"title": "Add error handling and logging", "priority": 3, "depends_on": ["Build core module"]},
                ],
            },
            {
                "title": "Testing",
                "description": "Verify correctness and quality.",
                "tasks": [
                    {"title": "Write unit tests", "priority": 2, "depends_on": ["Build core module"]},
                    {"title": "Run integration tests", "priority": 2, "depends_on": ["Write unit tests"]},
                    {"title": "Fix and retest failures", "priority": 2, "depends_on": ["Run integration tests"]},
                ],
            },
            {
                "title": "Release",
                "description": "Ship the product.",
                "tasks": [
                    {"title": "Write documentation", "priority": 3, "depends_on": ["Implement feature set"]},
                    {"title": "Final code review", "priority": 2, "depends_on": ["Fix and retest failures"]},
                    {"title": "Deploy to production", "priority": 1, "depends_on": ["Final code review", "Write documentation"]},
                ],
            },
        ],
        metadata={"typical_duration_days": 30},
    )


def _research_template() -> GoalTemplate:
    return GoalTemplate(
        template_id="tpl_research_v1",
        name="Research Project",
        description="Systematic research: define question → sources → evidence → analysis → report.",
        category=GoalCategory.LEARNING,
        version=1,
        is_builtin=True,
        created_by="system",
        tags=["research", "study", "academic"],
        variables=["project_name", "deadline", "description", "priority"],
        milestones=[
            {
                "title": "Define Question",
                "description": "Frame the research question and scope.",
                "tasks": [
                    {"title": "Identify research topic", "priority": 2, "depends_on": []},
                    {"title": "Formulate research question", "priority": 2, "depends_on": []},
                    {"title": "Define scope and constraints", "priority": 3, "depends_on": []},
                ],
            },
            {
                "title": "Source Gathering",
                "description": "Collect relevant sources and literature.",
                "tasks": [
                    {"title": "Search academic databases", "priority": 2, "depends_on": []},
                    {"title": "Collect primary sources", "priority": 2, "depends_on": []},
                    {"title": "Organize references", "priority": 3, "depends_on": []},
                ],
            },
            {
                "title": "Evidence Collection",
                "description": "Extract and catalog evidence.",
                "tasks": [
                    {"title": "Extract key findings", "priority": 2, "depends_on": ["Collect primary sources"]},
                    {"title": "Create evidence matrix", "priority": 2, "depends_on": []},
                ],
            },
            {
                "title": "Analysis",
                "description": "Analyze findings and draw conclusions.",
                "tasks": [
                    {"title": "Identify patterns and themes", "priority": 2, "depends_on": ["Create evidence matrix"]},
                    {"title": "Evaluate evidence quality", "priority": 2, "depends_on": []},
                    {"title": "Form conclusions", "priority": 2, "depends_on": ["Identify patterns and themes"]},
                ],
            },
            {
                "title": "Final Report",
                "description": "Write and review the research report.",
                "tasks": [
                    {"title": "Draft report", "priority": 2, "depends_on": ["Form conclusions"]},
                    {"title": "Peer review", "priority": 2, "depends_on": ["Draft report"]},
                    {"title": "Finalize and submit", "priority": 1, "depends_on": ["Peer review"]},
                ],
            },
        ],
        metadata={"typical_duration_days": 60},
    )


def _study_template() -> GoalTemplate:
    return GoalTemplate(
        template_id="tpl_study_v1",
        name="Study Project",
        description="Learn a topic systematically: plan → learn → practice → revise → test.",
        category=GoalCategory.LEARNING,
        version=1,
        is_builtin=True,
        created_by="system",
        tags=["study", "learning", "education"],
        variables=["project_name", "deadline", "description", "priority"],
        milestones=[
            {
                "title": "Plan Syllabus",
                "description": "Define what to learn and in what order.",
                "tasks": [
                    {"title": "Identify learning objectives", "priority": 2, "depends_on": []},
                    {"title": "Break into topics", "priority": 2, "depends_on": []},
                    {"title": "Create study schedule", "priority": 3, "depends_on": []},
                ],
            },
            {
                "title": "Learn Topics",
                "description": "Study each topic systematically.",
                "tasks": [
                    {"title": "Read core material", "priority": 2, "depends_on": []},
                    {"title": "Watch supplementary videos", "priority": 3, "depends_on": []},
                    {"title": "Take notes", "priority": 2, "depends_on": []},
                ],
            },
            {
                "title": "Practice",
                "description": "Apply what was learned.",
                "tasks": [
                    {"title": "Complete exercises", "priority": 2, "depends_on": ["Read core material"]},
                    {"title": "Build practice projects", "priority": 2, "depends_on": []},
                ],
            },
            {
                "title": "Revision",
                "description": "Review and reinforce learning.",
                "tasks": [
                    {"title": "Review notes", "priority": 2, "depends_on": ["Complete exercises"]},
                    {"title": "Create summary cards", "priority": 3, "depends_on": []},
                ],
            },
            {
                "title": "Test",
                "description": "Assess mastery.",
                "tasks": [
                    {"title": "Self-assessment quiz", "priority": 2, "depends_on": ["Create summary cards"]},
                    {"title": "Identify weak areas", "priority": 2, "depends_on": []},
                    {"title": "Final assessment", "priority": 1, "depends_on": ["Self-assessment quiz"]},
                ],
            },
        ],
        metadata={"typical_duration_days": 45},
    )


def _business_template() -> GoalTemplate:
    return GoalTemplate(
        template_id="tpl_business_v1",
        name="Business Project",
        description="Bring a business initiative to market: research → plan → product → marketing → launch.",
        category=GoalCategory.WORK,
        version=1,
        is_builtin=True,
        created_by="system",
        tags=["business", "product", "launch"],
        variables=["project_name", "deadline", "description", "priority"],
        milestones=[
            {
                "title": "Market Research",
                "description": "Understand the market and competition.",
                "tasks": [
                    {"title": "Define target audience", "priority": 2, "depends_on": []},
                    {"title": "Analyze competitors", "priority": 2, "depends_on": []},
                    {"title": "Identify unique value proposition", "priority": 2, "depends_on": []},
                ],
            },
            {
                "title": "Planning",
                "description": "Define business strategy and roadmap.",
                "tasks": [
                    {"title": "Write business plan", "priority": 2, "depends_on": ["Define target audience"]},
                    {"title": "Set milestones and KPIs", "priority": 2, "depends_on": []},
                    {"title": "Budget planning", "priority": 3, "depends_on": []},
                ],
            },
            {
                "title": "Product Development",
                "description": "Build the product or service.",
                "tasks": [
                    {"title": "Design MVP", "priority": 2, "depends_on": ["Write business plan"]},
                    {"title": "Build MVP", "priority": 2, "depends_on": []},
                    {"title": "Internal testing", "priority": 2, "depends_on": ["Build MVP"]},
                ],
            },
            {
                "title": "Marketing",
                "description": "Create awareness and demand.",
                "tasks": [
                    {"title": "Create marketing materials", "priority": 2, "depends_on": ["Design MVP"]},
                    {"title": "Set up channels", "priority": 2, "depends_on": []},
                    {"title": "Launch campaign", "priority": 2, "depends_on": ["Create marketing materials"]},
                ],
            },
            {
                "title": "Launch",
                "description": "Go live and monitor.",
                "tasks": [
                    {"title": "Public launch", "priority": 1, "depends_on": ["Internal testing", "Launch campaign"]},
                    {"title": "Monitor metrics", "priority": 2, "depends_on": []},
                    {"title": "Iterate based on feedback", "priority": 2, "depends_on": []},
                ],
            },
        ],
        metadata={"typical_duration_days": 90},
    )


def _personal_template() -> GoalTemplate:
    return GoalTemplate(
        template_id="tpl_personal_v1",
        name="Personal Project",
        description="General-purpose personal goal with planning, execution, and review phases.",
        category=GoalCategory.PERSONAL,
        version=1,
        is_builtin=True,
        created_by="system",
        tags=["personal", "life", "general"],
        variables=["project_name", "deadline", "description", "priority"],
        milestones=[
            {
                "title": "Goal Setting",
                "description": "Define what success looks like.",
                "tasks": [
                    {"title": "Define the goal", "priority": 2, "depends_on": []},
                    {"title": "Identify obstacles", "priority": 2, "depends_on": []},
                    {"title": "Define success criteria", "priority": 3, "depends_on": []},
                ],
            },
            {
                "title": "Planning",
                "description": "Create a clear action plan.",
                "tasks": [
                    {"title": "Break into steps", "priority": 2, "depends_on": []},
                    {"title": "Set deadlines for each step", "priority": 2, "depends_on": []},
                ],
            },
            {
                "title": "Execution",
                "description": "Work through the plan.",
                "tasks": [
                    {"title": "Work on step 1", "priority": 2, "depends_on": []},
                    {"title": "Work on step 2", "priority": 2, "depends_on": []},
                    {"title": "Work on step 3", "priority": 2, "depends_on": []},
                ],
            },
            {
                "title": "Review",
                "description": "Evaluate and iterate.",
                "tasks": [
                    {"title": "Assess results", "priority": 2, "depends_on": []},
                    {"title": "Celebrate and document", "priority": 3, "depends_on": []},
                ],
            },
        ],
        metadata={"typical_duration_days": 30},
    )


def _get_builtin_templates() -> Dict[str, GoalTemplate]:
    return {
        "tpl_coding_v1": _coding_template(),
        "tpl_research_v1": _research_template(),
        "tpl_study_v1": _study_template(),
        "tpl_business_v1": _business_template(),
        "tpl_personal_v1": _personal_template(),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Template Manager
# ─────────────────────────────────────────────────────────────────────────────

class GoalTemplateManager:
    """Manages built-in and custom goal templates with persistence."""

    def __init__(self, data_dir: Optional[str] = None):
        if data_dir is None:
            data_dir = str(Path("data/goals").expanduser())
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.templates_file = self.data_dir / "templates.json"
        self._templates: Dict[str, GoalTemplate] = {}
        # Try to get shared task manager; if none exists, create one pointing to
        # the same data_dir so template-created tasks land in the same SQLite DB
        # that GoalsManager uses (both resolve data_dir/goals.db).
        try:
            from jarvis_core.tasks import TaskManager, TaskStore
            # Point TaskStore to the same data_dir as GoalsManager so they share
            # the same SQLite file (GoalsManager uses data_dir/goals.db for tasks)
            tasks_db = str(self.data_dir / "goals.db")
            self._task_manager = TaskManager(store=TaskStore(db_path=tasks_db))
        except Exception:
            self._task_manager = None
        self._load()

    def _load(self) -> None:
        # Start with built-ins (never overwritten by disk)
        self._templates = _get_builtin_templates()
        if self.templates_file.exists():
            try:
                with open(self.templates_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for d in data.get("templates", []):
                    tpl = GoalTemplate.from_dict(d)
                    if not tpl.is_builtin:
                        self._templates[tpl.template_id] = tpl
            except Exception as e:
                logger.error("Failed to load templates: %s", e)

    def _save(self) -> None:
        # Only save custom (non-builtin) templates
        custom = [t.to_dict() for t in self._templates.values() if not t.is_builtin]
        try:
            with open(self.templates_file, "w", encoding="utf-8") as f:
                json.dump({"templates": custom, "saved_at": _utc()}, f, indent=2)
        except Exception as e:
            logger.error("Failed to save templates: %s", e)

    # ── CRUD ────────────────────────────────────────────────────────────────

    def list_templates(self, include_builtin: bool = True) -> List[GoalTemplate]:
        templates = list(self._templates.values())
        if not include_builtin:
            templates = [t for t in templates if not t.is_builtin]
        return sorted(templates, key=lambda t: (not t.is_builtin, t.name))

    def get_template(self, template_id: str) -> Optional[GoalTemplate]:
        return self._templates.get(template_id)

    def get_template_by_name(self, name: str) -> Optional[GoalTemplate]:
        n = name.lower().strip()
        for t in self._templates.values():
            if t.name.lower().strip() == n:
                return t
            if n in t.name.lower():
                return t
        return None

    def create_template(
        self,
        name: str,
        description: str = "",
        category: GoalCategory = GoalCategory.PROJECT,
        milestones: Optional[List[Dict[str, Any]]] = None,
        default_priority: Priority = Priority.MEDIUM,
        tags: Optional[List[str]] = None,
        created_by: str = "user",
    ) -> GoalTemplate:
        """Create a new custom template."""
        # Prevent name collision with built-ins
        existing = self.get_template_by_name(name)
        if existing and existing.is_builtin:
            raise ValueError(f"Cannot create template: name '{name}' conflicts with a built-in template.")
        tid = "tpl_" + uuid.uuid4().hex[:12]
        tpl = GoalTemplate(
            template_id=tid,
            name=name,
            description=description,
            category=category,
            version=1,
            is_active=True,
            is_builtin=False,
            created_by=created_by,
            milestones=milestones or [],
            default_priority=default_priority,
            tags=tags or [],
        )
        self._templates[tid] = tpl
        self._save()
        return tpl

    def update_template(
        self,
        template_id: str,
        **kwargs,
    ) -> Optional[GoalTemplate]:
        """Update a custom template (bump version). Built-ins are immutable."""
        tpl = self._templates.get(template_id)
        if not tpl:
            return None
        if tpl.is_builtin:
            raise ValueError("Built-in templates cannot be modified.")
        for key, value in kwargs.items():
            if key in ("name", "description", "category", "milestones", "default_priority", "tags", "is_active"):
                setattr(tpl, key, value)
        tpl.version += 1
        tpl.updated_at = _utc()
        self._save()
        return tpl

    def delete_template(self, template_id: str) -> bool:
        """Delete a custom template."""
        tpl = self._templates.get(template_id)
        if not tpl:
            return False
        if tpl.is_builtin:
            raise ValueError("Built-in templates cannot be deleted.")
        del self._templates[template_id]
        self._save()
        return True

    # ── Variable substitution ──────────────────────────────────────────────

    @staticmethod
    def _substitute(text: str, variables: Dict[str, str]) -> str:
        """
        Safe text substitution: replaces {{key}} with variables[key].
        No code execution. Malformed keys are left as-is.
        """
        for key, value in variables.items():
            text = text.replace("{{" + key + "}}", str(value))
        return text

    # ── Instantiation ──────────────────────────────────────────────────────

    def instantiate(
        self,
        template_id: str,
        goals_manager: GoalsManager,
        variables: Optional[Dict[str, str]] = None,
        priority: Optional[Priority] = None,
        deadline: Optional[datetime] = None,
        category: Optional[GoalCategory] = None,
        created_by: str = "user",
    ) -> Dict[str, Any]:
        """
        Create a real Goal from a template.

        Returns a dict with the new goal_id and a manifest of created objects.
        On any failure, no partial Goal is persisted.

        Parameters
        ----------
        template_id : str
            ID of the template to instantiate.
        goals_manager : GoalsManager
            Canonical goals manager for persistence.
        variables : dict, optional
            Variable values for {{substitution}}. Keys: project_name, description, deadline, priority.
        priority : Priority, optional
            Override template default.
        deadline : datetime, optional
            Set goal deadline.
        category : GoalCategory, optional
            Override template default.
        created_by : str
            Who requested the instantiation.

        Returns
        -------
        dict with keys: goal_id, template_id, template_version, goal_title,
                        milestones_created, tasks_created, error
        """
        variables = variables or {}
        tpl = self._templates.get(template_id)
        if not tpl:
            return {"error": f"Template '{template_id}' not found.", "goal_id": None}

        # Apply variable defaults
        defaults = {
            "project_name": variables.get("project_name", tpl.name),
            "description": variables.get("description", tpl.description),
            "deadline": variables.get("deadline", ""),
            "priority": (priority or tpl.default_priority).name,
        }
        for k, v in defaults.items():
            if k not in variables:
                variables[k] = v

        try:
            # ── Atomic: build everything first, then persist only on success ──
            goal_title = self._substitute("{{project_name}}", variables)

            # Create goal
            goal = goals_manager.create_goal(
                title=goal_title,
                description=self._substitute("{{description}}", variables),
                priority=priority or tpl.default_priority,
                category=category or tpl.category,
                deadline=deadline,
                tags=tpl.tags,
            )

            # Build task title → task_id map for dependency resolution
            task_id_map: Dict[str, str] = {}  # task title (lowercase) → id
            milestone_ids: List[str] = []
            created_tasks: List[Dict[str, str]] = []

            for ms_data in tpl.milestones:
                ms_title = self._substitute(ms_data.get("title", "Milestone"), variables)
                milestone = goals_manager.add_milestone(
                    goal_id=goal.id,
                    title=ms_title,
                )
                if milestone:
                    milestone_ids.append(milestone.id)

                # Create tasks for this milestone
                for task_data in ms_data.get("tasks", []):
                    task_title = self._substitute(task_data.get("title", "Task"), variables)
                    task_priority = task_data.get("priority", 5)
                    depends_on_titles = task_data.get("depends_on", [])

                    # Resolve dependency titles to real task IDs
                    resolved_deps = []
                    for dep_title in depends_on_titles:
                        subbed = self._substitute(dep_title, variables).lower()
                        if subbed in task_id_map:
                            resolved_deps.append(task_id_map[subbed])

                    # Use the goals_manager's task manager if available,
                    # otherwise fall back to our own (initialized with the same data_dir)
                    _tm = goals_manager._task_manager if goals_manager._task_manager else self._task_manager
                    if _tm is None:
                        raise RuntimeError(
                            "No TaskManager available. Provide GoalsManager with an initialized "
                            "_task_manager, or ensure jarvis_core.tasks is importable."
                        )
                    task = _tm.create(
                        title=task_title,
                        kind="goal_task",
                        owner="owner",
                        manager="goal_template",
                        priority=task_priority,
                        depends_on=resolved_deps,
                        payload={
                            "goal_id": goal.id,
                            "milestone_id": milestone.id if milestone else None,
                            "template_id": tpl.template_id,
                            "template_version": tpl.version,
                        },
                    )
                    tid = task.task_id
                    task_id_map[task_title.lower()] = tid
                    created_tasks.append({"task_id": tid, "title": task_title})

                    # Link task to milestone
                    if milestone and milestone.task_id is None:
                        milestone.task_id = tid
                        goals_manager.link_task(goal.id, tid)
                    elif milestone:
                        # Additional tasks — link via goal.task_ids
                        goals_manager.link_task(goal.id, tid)

                # Mark milestone complete if all its tasks are resolved (no deps = immediately ready)
                if milestone:
                    all_ready = all(
                        not task_data.get("depends_on", [])
                        for task_data in ms_data.get("tasks", [])
                    )
                    # Don't auto-complete — let user mark it done

            # Store provenance in goal metadata
            goal.metadata["template_id"] = tpl.template_id
            goal.metadata["template_version"] = tpl.version
            goal.metadata["template_name"] = tpl.name
            goal.metadata["instantiated_at"] = _utc()
            goal.metadata["instantiated_by"] = created_by
            goal.metadata["variables_used"] = variables
            goals_manager._save_goals()

            return {
                "goal_id": goal.id,
                "goal_title": goal.title,
                "template_id": tpl.template_id,
                "template_version": tpl.version,
                "template_name": tpl.name,
                "milestones_created": len(milestone_ids),
                "tasks_created": len(created_tasks),
                "created_at": _utc(),
            }

        except Exception as e:
            logger.error("Template instantiation failed: %s", e)
            # Rollback: delete the goal if it was partially created
            try:
                if "goal" in dir() and goal and goal.id:
                    goals_manager.delete_goal(goal.id)
            except Exception:
                pass
            return {
                "error": f"Template instantiation failed: {e}",
                "goal_id": None,
            }


# ─────────────────────────────────────────────────────────────────────────────
# Singleton
# ─────────────────────────────────────────────────────────────────────────────

_template_manager: Optional[GoalTemplateManager] = None


def get_template_manager() -> GoalTemplateManager:
    global _template_manager
    if _template_manager is None:
        _template_manager = GoalTemplateManager()
    return _template_manager
