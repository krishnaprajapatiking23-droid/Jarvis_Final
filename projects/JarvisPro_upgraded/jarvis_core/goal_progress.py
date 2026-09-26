"""
Goal Progress Reports — Phase 15 Feature A.

Calculates real progress from persisted Goal → Milestone → Task data.
NEVER hard-codes percentages. Every figure is derived from actual task/milestone state.

Progress algorithm:
  - A goal has milestones; each milestone has a linked task (via task_id).
  - A task contributes to milestone progress when it is COMPLETED.
  - A milestone contributes to goal progress when ALL its tasks are COMPLETED.
  - FAILED / CANCELLED / ROLLED_BACK tasks do NOT count as completed.
  - A milestone with no linked task contributes 0 until explicitly completed.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# Task states — which ones count as "done" for progress purposes
_COMPLETED_STATES = {"completed"}
_PROGRESS_STATES = {"completed", "running", "queued", "planning", "paused", "waiting"}
_BLOCKED_STATES = {"failed", "cancelled", "rolled_back"}


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ─────────────────────────────────────────────────────────────────────────────
# Core calculation engine
# ─────────────────────────────────────────────────────────────────────────────

def calculate_goal_progress(
    goal,
    task_manager=None,
) -> Dict[str, Any]:
    """
    Calculate progress for a Goal object.

    Algorithm:
      milestone_progress = completed_tasks / total_tasks_in_milestone
      goal_progress      = sum(milestone_progress) / num_milestones_with_content

    Milestones with no tasks: contribute 0 to the average denominator
    (they must be explicitly marked completed).

    Parameters
    ----------
    goal : Goal
        The goal to calculate progress for.
    task_manager : TaskManager, optional
        If provided, uses real TaskManager task states.
        Otherwise falls back to milestone.completed bool.

    Returns
    -------
    dict with keys: overall_progress (0.0–1.0), milestone_progresses, task_summary
    """
    if not goal:
        return {
            "overall_progress": 0.0,
            "milestone_progresses": [],
            "task_summary": {"total": 0, "completed": 0, "running": 0, "pending": 0, "blocked": 0},
            "calculation": "no_goal",
        }

    milestones = goal.milestones or []
    milestone_progresses: List[Dict[str, Any]] = []
    total_task_count = 0
    completed_task_count = 0
    running_task_count = 0
    pending_task_count = 0
    blocked_task_count = 0
    milestones_with_content = 0
    milestone_progress_sum = 0.0

    for m in milestones:
        m_progress: float
        m_tasks_total = 0
        m_tasks_completed = 0
        m_tasks_running = 0
        m_tasks_blocked = 0
        m_linked_blocked: List[Dict[str, str]] = []

        if task_manager and m.task_id:
            # Real task state from TaskManager
            try:
                task = task_manager.get(m.task_id)
                m_tasks_total = 1
                total_task_count += 1
                state = task.state
                if state in _COMPLETED_STATES:
                    m_tasks_completed = 1
                    completed_task_count += 1
                elif state in _PROGRESS_STATES:
                    if state == "running":
                        running_task_count += 1
                    else:
                        pending_task_count += 1
                elif state in _BLOCKED_STATES:
                    m_tasks_blocked = 1
                    blocked_task_count += 1
                    m_linked_blocked.append({
                        "task_id": task.task_id,
                        "title": task.title,
                        "state": state,
                        "failure_reason": task.failure_reason or "",
                    })
            except KeyError:
                # Task ID exists on milestone but task not found — treat as blocked
                m_tasks_blocked = 1
                blocked_task_count += 1
                m_linked_blocked.append({
                    "task_id": m.task_id,
                    "title": "[task not found]",
                    "state": "orphaned",
                    "failure_reason": "linked task does not exist in TaskManager",
                })
        else:
            # Fallback: milestone.completed boolean (no TaskManager available)
            # Keep m_tasks_total = 0 so this milestone goes through the
            # milestone-only path below.  Both complete and incomplete milestones
            # contribute to the denominator so that "1 of 2 complete = 50%".
            m_tasks_total = 0
            m_tasks_completed = 0
            if not m.completed:
                pending_task_count += 1

        if m_tasks_total > 0:
            m_progress = m_tasks_completed / m_tasks_total
            milestones_with_content += 1
            milestone_progress_sum += m_progress
        else:
            # Milestone with no linked tasks — contribution is 1.0 if completed,
            # 0.0 if not.  Always count toward the denominator so that the
            # milestone_completion_ratio fallback (lines 157-161) gives the
            # expected result: 1 complete / 2 total = 50%.
            m_progress = 1.0 if m.completed else 0.0
            milestones_with_content += 1
            milestone_progress_sum += m_progress

        milestone_progresses.append({
            "milestone_id": m.id,
            "title": m.title,
            "progress": round(m_progress, 4),
            "completed": bool(m.completed) or m_tasks_completed > 0,
            "task_id": m.task_id,
            "deadline": m.deadline.isoformat() if m.deadline else None,
            "completed_at": m.completed_at.isoformat() if m.completed_at else None,
            "tasks_in_milestone": m_tasks_total,
            "tasks_completed": m_tasks_completed,
            "linked_blocked": m_linked_blocked,
        })

    if milestones_with_content > 0:
        overall = milestone_progress_sum / milestones_with_content
        calc_method = "milestone_task_weighted"
    elif milestones:
        # All milestones are empty (no tasks) — use milestone completion ratio
        completed_milestones = sum(1 for m in milestones if m.completed)
        overall = completed_milestones / len(milestones)
        calc_method = "milestone_completion_ratio"
    else:
        overall = 0.0
        calc_method = "no_goal"

    return {
        "overall_progress": round(overall, 4),
        "milestone_progresses": milestone_progresses,
        "task_summary": {
            "total": total_task_count,
            "completed": completed_task_count,
            "running": running_task_count,
            "pending": pending_task_count,
            "blocked": blocked_task_count,
        },
        "calculation": calc_method,
        "milestones_with_content": milestones_with_content,
        "total_milestones": len(milestones),
    }


def detect_blockers(goal, task_manager=None) -> List[Dict[str, Any]]:
    """
    Identify real blockers in a goal's task graph.

    A task is blocked when:
      - It depends on another task that FAILED / CANCELLED / ROLLED_BACK.
      - Its linked milestone has no task but is not complete.

    Returns a list of blocker records.
    """
    blockers: List[Dict[str, Any]] = []

    if not goal:
        return blockers

    for m in goal.milestones or []:
        if not m.task_id:
            if not m.completed:
                blockers.append({
                    "type": "orphaned_milestone",
                    "cause": "milestone has no linked task and is not complete",
                    "affected_milestone_id": m.id,
                    "affected_milestone_title": m.title,
                    "affected_goal_id": goal.id,
                })
            continue

        if not task_manager:
            continue

        try:
            task = task_manager.get(m.task_id)
        except KeyError:
            continue

        # Check if dependencies are unmet
        for dep_id in task.depends_on:
            try:
                dep = task_manager.get(dep_id)
            except KeyError:
                blockers.append({
                    "type": "missing_dependency",
                    "cause": f"dependency {dep_id} not found",
                    "affected_task_id": task.task_id,
                    "affected_task_title": task.title,
                    "affected_milestone_id": m.id,
                    "affected_goal_id": goal.id,
                })
                continue

            if dep.state in _BLOCKED_STATES:
                blockers.append({
                    "type": "failed_dependency",
                    "cause": f"dependency '{dep.title}' ({dep_id}) is {dep.state}",
                    "affected_task_id": task.task_id,
                    "affected_task_title": task.title,
                    "affected_milestone_id": m.id,
                    "affected_goal_id": goal.id,
                    "dependency_task_id": dep_id,
                    "dependency_state": dep.state,
                    "dependency_failure_reason": dep.failure_reason or "",
                })

    return blockers


def deadline_status(goal) -> Dict[str, Any]:
    """Calculate deadline analysis for a goal."""
    if not goal or not goal.deadline:
        return {
            "has_deadline": False,
            "status": "NO_DEADLINE",
            "deadline": None,
            "remaining_seconds": None,
        }

    now = datetime.now(timezone.utc)
    deadline = goal.deadline
    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=timezone.utc)

    delta = deadline - now
    remaining_s = delta.total_seconds()

    if remaining_s < 0:
        status = "OVERDUE"
    elif remaining_s < 86400:  # < 24 hours
        status = "AT_RISK"
    else:
        status = "ON_TRACK"

    return {
        "has_deadline": True,
        "deadline": goal.deadline.isoformat(),
        "remaining_seconds": int(remaining_s),
        "remaining_formatted": _format_duration(remaining_s),
        "status": status,
    }


def _format_duration(seconds: float) -> str:
    if seconds < 0:
        return "overdue"
    days = int(seconds // 86400)
    hours = int((seconds % 86400) // 3600)
    mins = int((seconds % 3600) // 60)
    if days > 0:
        return f"{days}d {hours}h"
    if hours > 0:
        return f"{hours}h {mins}m"
    return f"{mins}m"


def next_recommended_action(goal, task_manager=None) -> Optional[Dict[str, Any]]:
    """
    Return the logical next task to work on, based on:
      1. Startable tasks (dependencies met, not blocked) — prefer these
      2. Tasks already running — fall back if nothing is ready to start
    """
    if not goal or not task_manager:
        return None

    ready: List[Any] = []
    running_task = None

    for m in goal.milestones or []:
        if not m.task_id:
            continue
        try:
            task = task_manager.get(m.task_id)
        except KeyError:
            continue

        # Track running tasks as fallback (don't return early — prefer ready tasks)
        if task.state == "running" and running_task is None:
            running_task = (task, m)

        # Skip blocked/failed tasks
        if task.state in _BLOCKED_STATES:
            continue

        # Only add tasks in a genuinely startable state
        if task.state in ("created", "queued", "planning", "waiting", "paused"):
            deps_met = True
            for d_id in task.depends_on:
                try:
                    dep = task_manager.get(d_id)
                    if dep.state not in _COMPLETED_STATES:
                        deps_met = False
                        break
                except KeyError:
                    deps_met = False
                    break
            if deps_met:
                ready.append((task, m))

    # Prefer startable tasks; fall back to running task if nothing is ready
    if ready:
        task, m = min(ready, key=lambda x: (x[0].priority, x[0].created_at))
        return {
            "action": "start",
            "task_id": task.task_id,
            "title": task.title,
            "state": task.state,
            "priority": task.priority,
            "reason": f"Ready to start — all dependencies met, unblocks milestone '{m.title}'",
            "milestone_id": m.id,
            "milestone_title": m.title,
        }

    if running_task:
        task, m = running_task
        return {
            "action": "continue",
            "task_id": task.task_id,
            "title": task.title,
            "state": task.state,
            "reason": f"Task is currently running",
            "milestone_id": m.id,
            "milestone_title": m.title,
        }

    return None


# ─────────────────────────────────────────────────────────────────────────────
# Report generators
# ─────────────────────────────────────────────────────────────────────────────

def get_goal_progress(goal_id: str, goals_manager, task_manager=None) -> Dict[str, Any]:
    """Current-progress summary (lightweight)."""
    goal = goals_manager.get_goal(goal_id) if goals_manager else None
    if not goal:
        return {"error": f"goal {goal_id} not found"}
    progress = calculate_goal_progress(goal, task_manager)
    return {
        "goal_id": goal.id,
        "title": goal.title,
        "overall_progress": progress["overall_progress"],
        "overall_percent": round(progress["overall_progress"] * 100, 1),
        "task_summary": progress["task_summary"],
        "total_milestones": len(goal.milestones),
        "completed_milestones": sum(1 for m in goal.milestones if m.completed),
        "deadline_status": deadline_status(goal),
    }


def get_goal_task_breakdown(goal_id: str, goals_manager, task_manager=None) -> Dict[str, Any]:
    """Task-level breakdown for a goal."""
    goal = goals_manager.get_goal(goal_id) if goals_manager else None
    if not goal:
        return {"error": f"goal {goal_id} not found"}

    tasks: List[Dict[str, Any]] = []
    for m in goal.milestones or []:
        entry: Dict[str, Any] = {
            "milestone_id": m.id,
            "milestone_title": m.title,
            "milestone_completed": m.completed,
            "task": None,
        }
        if m.task_id and task_manager:
            try:
                task = task_manager.get(m.task_id)
                entry["task"] = {
                    "task_id": task.task_id,
                    "title": task.title,
                    "state": task.state,
                    "priority": task.priority,
                    "progress": task.progress,
                    "depends_on": task.depends_on,
                    "failure_reason": task.failure_reason,
                }
            except KeyError:
                entry["task"] = {"task_id": m.task_id, "title": "[not found]", "state": "orphaned"}
        elif m.task_id:
            entry["task"] = {"task_id": m.task_id, "title": "[no task manager]", "state": "unknown"}
        tasks.append(entry)

    return {
        "goal_id": goal.id,
        "title": goal.title,
        "breakdown": tasks,
    }


def generate_goal_report(goal_id: str, goals_manager, task_manager=None) -> Dict[str, Any]:
    """
    Full detailed goal progress report.
    """
    goal = goals_manager.get_goal(goal_id) if goals_manager else None
    if not goal:
        return {"error": f"goal {goal_id} not found", "report_id": None}

    report_id = f"RPT-{uuid.uuid4().hex[:10]}"
    progress = calculate_goal_progress(goal, task_manager)
    blockers = detect_blockers(goal, task_manager)
    dl = deadline_status(goal)
    next_action = next_recommended_action(goal, task_manager)

    completed_tasks = progress["task_summary"]["completed"]
    total_eligible = sum(
        1 for m in (goal.milestones or [])
        if m.task_id and (task_manager is None or m.task_id in task_manager.tasks)
    )

    return {
        "report_id": report_id,
        "generated_at": _utc(),

        # Goal identity
        "goal_id": goal.id,
        "title": goal.title,
        "description": goal.description,
        "status": goal.status.value if hasattr(goal.status, "value") else str(goal.status),
        "priority": goal.priority.name if hasattr(goal.priority, "name") else str(goal.priority),
        "category": goal.category.value if hasattr(goal.category, "value") else str(goal.category),
        "created_at": goal.created_at.isoformat() if goal.created_at else None,
        "deadline": goal.deadline.isoformat() if goal.deadline else None,

        # Progress
        "overall_progress": progress["overall_progress"],
        "overall_percent": round(progress["overall_progress"] * 100, 1),
        "calculation": progress["calculation"],

        # Milestones
        "milestones": {
            "total": len(goal.milestones),
            "completed": sum(1 for m in goal.milestones if m.completed),
            "remaining": sum(1 for m in goal.milestones if not m.completed),
            "detail": progress["milestone_progresses"],
        },

        # Tasks
        "tasks": {
            "total": total_eligible,
            "completed": completed_tasks,
            "running": progress["task_summary"]["running"],
            "pending": progress["task_summary"]["pending"],
            "blocked": progress["task_summary"]["blocked"],
        },

        # Deadline
        "deadline_analysis": dl,

        # Blockers
        "blockers": {
            "count": len(blockers),
            "items": blockers,
        },

        # Next action
        "next_action": next_action,

        # Metadata
        "calculation_detail": {
            "milestones_with_content": progress.get("milestones_with_content", 0),
            "total_milestones": progress.get("total_milestones", 0),
        },
    }


def get_milestone_progress(
    goal_id: str, milestone_id: str, goals_manager, task_manager=None
) -> Dict[str, Any]:
    """Progress report for one specific milestone."""
    goal = goals_manager.get_goal(goal_id) if goals_manager else None
    if not goal:
        return {"error": f"goal {goal_id} not found"}
    m = next((x for x in goal.milestones if x.id == milestone_id), None)
    if not m:
        return {"error": f"milestone {milestone_id} not found in goal {goal_id}"}

    progress = calculate_goal_progress(goal, task_manager)
    m_progress = next(
        (x for x in progress["milestone_progresses"] if x["milestone_id"] == milestone_id),
        None,
    )

    return {
        "goal_id": goal.id,
        "milestone_id": m.id,
        "title": m.title,
        "progress": m_progress["progress"] if m_progress else 0.0,
        "completed": bool(m.completed),
        "task_id": m.task_id,
        "deadline": m.deadline.isoformat() if m.deadline else None,
        "completed_at": m.completed_at.isoformat() if m.completed_at else None,
        "linked_blocked": m_progress["linked_blocked"] if m_progress else [],
    }


def get_goal_summary(goals_manager, task_manager=None) -> Dict[str, Any]:
    """Summary across all active goals."""
    all_goals = goals_manager.get_all_goals() if goals_manager else []
    rows: List[Dict[str, Any]] = []
    for g in all_goals:
        p = calculate_goal_progress(g, task_manager)
        dl = deadline_status(g)
        rows.append({
            "goal_id": g.id,
            "title": g.title,
            "status": g.status.value if hasattr(g.status, "value") else str(g.status),
            "overall_progress": p["overall_progress"],
            "overall_percent": round(p["overall_progress"] * 100, 1),
            "deadline_status": dl.get("status", "NO_DEADLINE"),
            "deadline": g.deadline.isoformat() if g.deadline else None,
            "total_milestones": len(g.milestones),
            "completed_milestones": sum(1 for m in g.milestones if m.completed),
            "blocked_tasks": p["task_summary"]["blocked"],
        })
    return {
        "goals": rows,
        "total": len(rows),
        "generated_at": _utc(),
    }
