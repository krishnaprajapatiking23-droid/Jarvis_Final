"""
jarvis_core — Jarvis Pro core utilities and command handlers.

Exports the Goal Progress Report and Goal Template command handlers
for integration with the BrainV2 pipeline.

Usage from BrainV2:
    from jarvis_core import process_goal_command
    result = process_goal_command(command)
    if result:
        return self._conversation_reply(understanding, result, "goal")

Or standalone:
    from jarvis_core import get_goals_manager, get_task_manager, get_template_manager
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

# Lazy imports to avoid circular dependencies at import time
_goals_manager: Any = None
_task_manager: Any = None
_template_manager: Any = None


def _gm():
    global _goals_manager
    if _goals_manager is None:
        try:
            from goals.manager import get_goals_manager as _g
            _goals_manager = _g()
        except Exception:
            try:
                from goals.manager import GoalsManager
                _goals_manager = GoalsManager()
            except Exception:
                _goals_manager = None
    return _goals_manager


def _tm():
    global _task_manager
    if _task_manager is None:
        try:
            from jarvis_core.tasks import TaskManager
            _task_manager = TaskManager()
        except Exception:
            try:
                from jarvis_core.tasks import get_task_manager
                _task_manager = get_task_manager()
            except Exception:
                _task_manager = None
    return _task_manager


def _tp():
    global _template_manager
    if _template_manager is None:
        try:
            from jarvis_core.goal_templates import get_template_manager
            _template_manager = get_template_manager()
        except Exception:
            _template_manager = None
    return _template_manager


# ─────────────────────────────────────────────────────────────────────────────
# Keyword sets for intent detection
# ─────────────────────────────────────────────────────────────────────────────

_PROGRESS_KEYWORDS = re.compile(
    r"\b(progress|report|status|how\s+(?:is|are|going)|"
    r"(?:show|give|tell).{0,30}(?:goal|progress|status)|"
    r"milestone\s+(?:progress|status)|"
    r"goal\s+(?:progress|status)|"
    r"(?:how\s+many|many)\s+(?:tasks?|milestones?)\s+(?:left|remaining|done)|"
    r"blocker|blocking|next\s+action|what.*work.*on\s+next)\b",
    re.IGNORECASE,
)

_TEMPLATE_KEYWORDS = re.compile(
    r"\b(templates?|goal\s+template|project\s+template|"
    r"create\s+.+\s+from\s+template|"
    r"use\s+template|instantiate|from\s+the\s+coding|from\s+the\s+research|"
    r"coding\s+template|research\s+template|study\s+template|"
    r"business\s+template|personal\s+template|"
    r"my\s+template|custom\s+template|"
    r"show\s+templates|list\s+templates?|"
    r"delete\s+template|edit\s+template)\b",
    re.IGNORECASE,
)

# ─────────────────────────────────────────────────────────────────────────────
# Goal Progress Report handler
# ─────────────────────────────────────────────────────────────────────────────

def _handle_progress(command: str) -> Optional[Dict[str, Any]]:
    """
    Handle goal progress / status / report commands.
    Returns a result dict or None if the command doesn't match.
    """
    from jarvis_core.goal_progress import (
        generate_goal_report,
        get_goal_progress,
        get_goal_summary,
        get_milestone_progress,
        get_goal_task_breakdown,
    )

    gm = _gm()
    tm = gm._task_manager if (gm and gm._task_manager) else _tm()
    text = command.lower()

    # --- "Show all goals" / "goal summary" ---
    if re.search(r"\b(goal\s+summary|all\s+goals?|show\s+(?:my\s+)?goals?)\b", text):
        summary = get_goal_summary(gm, tm)
        rows = summary.get("goals", [])
        if not rows:
            return {
                "type": "goal_progress",
                "reply": "You have no active goals yet. Create one with 'create a goal' or 'create a goal from template'.",
                "goals": [],
            }
        lines = []
        for g in rows:
            pct = g.get("overall_percent", 0)
            dl = g.get("deadline_status", "NO_DEADLINE")
            lines.append(
                f"  • {g['title']} — {pct}% complete [{dl}]"
            )
        reply = "Here are your active goals:\n" + "\n".join(lines)
        return {"type": "goal_progress", "reply": reply, "goals": rows}

    # --- "Show my goal progress" / "how is my goal going" ---
    if re.search(r"\b(goal\s+progress|how\s+is.*going|how\s+are.*going|"
                 r"show.*progress|give.*progress|goal\s+status)\b", text):
        # Try to find the goal by name in the command
        goal = _find_goal_by_command(command, gm)
        if not goal:
            # Default to first active goal
            active = gm.get_active_goals() if gm else []
            goal = active[0] if active else None

        if not goal:
            return {
                "type": "goal_progress",
                "reply": "I couldn't find an active goal to report on. Create one first.",
            }

        report = generate_goal_report(goal.id, gm, tm)
        if "error" in report:
            return {"type": "goal_progress", "reply": report["error"]}

        pct = report.get("overall_percent", 0)
        total_ms = report.get("milestones", {}).get("total", 0)
        done_ms = report.get("milestones", {}).get("completed", 0)
        total_tasks = report.get("tasks", {}).get("total", 0)
        done_tasks = report.get("tasks", {}).get("completed", 0)
        dl_status = report.get("deadline_analysis", {}).get("status", "NO_DEADLINE")
        blockers = report.get("blockers", {}).get("count", 0)
        next_action = report.get("next_action")

        lines = [
            f"📊 **{report['title']}** — {pct}% complete",
            f"   Status: {report.get('status', 'active')} | Deadline: {dl_status}",
            f"   Milestones: {done_ms}/{total_ms} | Tasks: {done_tasks}/{total_tasks}",
        ]

        if blockers > 0:
            lines.append(f"   ⚠️  {blockers} blocker(s) detected")
        if next_action:
            lines.append(f"   ➡️  Next: *{next_action['title']}* (ready to start)")

        # Milestone breakdown
        for ms in report.get("milestones", {}).get("detail", []):
            pct_ms = round(ms["progress"] * 100)
            done = "✅" if ms["completed"] else "⬜"
            lines.append(f"   {done} {ms['title']}: {pct_ms}%")

        reply = "\n".join(lines)
        return {"type": "goal_progress", "reply": reply, "report": report}

    # --- "Show milestone X progress" ---
    m = re.search(r"milestone\s+.*?(\d+)", text)
    if m and gm:
        active = gm.get_active_goals()
        if active:
            goal = active[0]
            ms_id = None
            milestones = goal.milestones or []
            idx = int(m.group(1)) - 1
            if 0 <= idx < len(milestones):
                ms_id = milestones[idx].id
                mp = get_milestone_progress(goal.id, ms_id, gm, tm)
                reply = (f"Milestone: **{mp['title']}** — "
                         f"{round(mp['progress'] * 100)}% complete")
                return {"type": "goal_progress", "reply": reply, "milestone": mp}

    # --- "What should I work on next" ---
    if re.search(r"\b(what.*(work|focus|do)\s+next|next\s+action|recommend)\b", text):
        from jarvis_core.goal_progress import next_recommended_action
        goal = _find_goal_by_command(command, gm) or (gm.get_active_goals()[0] if gm and gm.get_active_goals() else None)
        if not goal:
            return {"type": "goal_progress", "reply": "No active goal found."}
        action = next_recommended_action(goal, tm)
        if action:
            reply = (f"Recommended next action: **{action['title']}**\n"
                     f"Reason: {action['reason']}\n"
                     f"Milestone: {action.get('milestone_title', 'N/A')}")
        else:
            reply = "No immediate next action available. All tasks may be blocked or completed."
        return {"type": "goal_progress", "reply": reply}

    # --- "Which tasks are blocking" ---
    if re.search(r"\b(blocker|blocking|blocked)\b", text):
        from jarvis_core.goal_progress import detect_blockers
        goal = _find_goal_by_command(command, gm) or (gm.get_active_goals()[0] if gm and gm.get_active_goals() else None)
        if not goal:
            return {"type": "goal_progress", "reply": "No active goal found."}
        blockers = detect_blockers(goal, tm)
        if not blockers:
            return {"type": "goal_progress", "reply": "No blockers detected for this goal. ✅"}
        lines = ["⚠️ **Blockers detected:**"]
        for b in blockers:
            lines.append(f"  • {b['type']}: {b.get('affected_task_title', b.get('affected_milestone_title', 'unknown'))} — {b['cause']}")
        return {"type": "goal_progress", "reply": "\n".join(lines), "blockers": blockers}

    return None


# ─────────────────────────────────────────────────────────────────────────────
# Goal Template handler
# ─────────────────────────────────────────────────────────────────────────────

def _handle_template(command: str) -> Optional[Dict[str, Any]]:
    """
    Handle goal template commands: list, create-from-template, create-template, etc.
    Returns a result dict or None if the command doesn't match.
    """
    from jarvis_core.goal_templates import get_template_manager

    tm = _tp()
    gm = _gm()
    # Share one TaskManager instance across GoalsManager, template instantiation,
    # and progress reporting so tasks land in the same SQLite DB.
    shared_tm = _tm()
    if gm and gm._task_manager is None:
        gm._task_manager = shared_tm
    # Prefer GoalsManager's injected TaskManager over singleton.
    task_mgr = gm._task_manager if (gm and gm._task_manager) else shared_tm
    text = command.lower()

    if tm is None:
        return None

    # --- "Show templates" / "list templates" ---
    if re.search(r"^\s*(show|list|view|display)\s+(goal\s+)?templates?\s*$", text) or \
       re.search(r"\b(show|list|view|display)\s+(?:goal\s+)?templates?\b", text):
        templates = tm.list_templates()
        if not templates:
            return {"type": "goal_template", "reply": "No templates available."}
        lines = ["📋 **Available Goal Templates:**"]
        for t in templates:
            tag = " [builtin]" if t.is_builtin else " [custom]"
            lines.append(f"  • **{t.name}**{tag} — {t.description[:60]}…")
            lines.append(f"    {len(t.milestones)} milestones | version {t.version}")
        return {"type": "goal_template", "reply": "\n".join(lines), "templates": [t.to_dict() for t in templates]}

    # --- "Create a goal from template X" ---
    m = None
    match_pattern = None  # 'p1', 'p2', 'p3', 'p4'

    # Pattern 1: "create a [goal name] goal/project from [template name] template"
    m = re.search(
        r"create\s+(?:a\s+|my\s+)?(.+?)\s+(?:goal|project)\s+from\s+(?:the\s+)?(.+?)\s*template",
        text,
    )
    if m:
        match_pattern = "p1"

    # Pattern 2: "create a [template name] template called [goal name]"
    if not m:
        m = re.search(
            r"create\s+(?:a\s+|my\s+)?(.+?)\s+template\s+(?:called|named|for)\s+(.+)",
            text,
        )
        if m:
            match_pattern = "p2"

    # Pattern 3: "use/instantiate [template name] template called [goal name]"
    if not m:
        m = re.search(
            r"(?:use|instantiate)\s+(.+?)\s+template\s+(?:called|named|for)\s+(.+)",
            text,
        )
        if m:
            match_pattern = "p3"

    # Pattern 4: "create a [type] called [goal name] from [template name] template"
    #   Template name is always at the END after "from", goal name between "called" and "from".
    #   Handles: "Create a coding project called Jarvis Mobile App from the Coding Project template."
    if not m:
        m = re.search(
            r"create\s+(.+?)\s+called\s+(.+?)\s+from\s+(?:the\s+)?(.+?)\s*template",
            text,
        )
        if m:
            match_pattern = "p4"

    if m:
        # Determine template vs goal name based on which pattern matched.
        # Pattern 1: g1=goal name, g2=template name
        # Pattern 2/3: g1=template name, g2=goal name
        # Pattern 4: g1=type+noun, g2=goal name, g3=template name
        g1 = (m.group(1) or "").strip()
        g2 = (m.group(2) or "").strip()
        template_name = None
        goal_name = None

        if match_pattern == "p4":
            # Pattern 4: group(1)=type phrase (e.g. "coding project"),
            #            group(2)=goal name (e.g. "Jarvis Mobile App"),
            #            group(3)=template name (e.g. "Coding Project")
            template_name = (m.group(3) or "").strip()
            goal_name = g2
        elif re.search(r"template\s+(?:called|named|for)", m.group(0)):
            # Pattern 2/3: g1=template name, g2=goal name
            template_name = g1
            goal_name = g2
        else:
            # Pattern 1: g1=goal name, g2=template name
            template_name = g2
            goal_name = g1

        tpl = tm.get_template_by_name(template_name)
        if not tpl:
            return {
                "type": "goal_template",
                "reply": f"I couldn't find a template matching '{template_name}'. "
                         "Try 'show goal templates' to see available options.",
            }

        # Extract goal name — already parsed above when handling called/named patterns
        if not goal_name:
            goal_name = (m.group(1) or "").strip() if m else tpl.name
        # Clean up leading "a " or "my " (e.g. "a Jarvis Mobile App" → "Jarvis Mobile App")
        goal_name = re.sub(r"^(?:a|my)\s+", "", goal_name, flags=re.IGNORECASE).strip()

        # Extract deadline if present
        deadline = None
        dl_m = re.search(r"deadline\s+(?:of\s+)?(.+?)(?:\s|$)", command, re.IGNORECASE)
        if dl_m:
            from dateutil.parser import parse as parse_date
            try:
                deadline = parse_date(dl_m.group(1))
            except Exception:
                pass

        variables = {
            "project_name": goal_name,
            "description": f"Created from template: {tpl.name}",
        }

        result = tm.instantiate(
            template_id=tpl.template_id,
            goals_manager=gm,
            variables=variables,
            deadline=deadline,
        )

        if "error" in result and result["error"]:
            return {
                "type": "goal_template",
                "reply": f"❌ Template instantiation failed: {result['error']}",
            }

        lines = [
            f"✅ Goal created from template: **{tpl.name}**",
            f"   Goal: **{result.get('goal_title', goal_name)}**",
            f"   Milestones: {result.get('milestones_created', 0)}",
            f"   Tasks: {result.get('tasks_created', 0)}",
            f"   View progress: 'show my goal progress'",
        ]
        return {
            "type": "goal_template",
            "reply": "\n".join(lines),
            "instantiation": result,
        }

    # --- "Create a goal template" ---
    if re.search(r"\b(create|new|add)\s+(?:a\s+)?(?:goal\s+)?template\b", text):
        m_name = re.search(r"(?:called|named|custom\s+)?(?:goal\s+)?template\s+['\"]?(.+?)['\"]?\s*$", text)
        if not m_name:
            return {
                "type": "goal_template",
                "reply": "To create a custom template, say: create a goal template called 'My Template' with milestones and tasks.",
            }
        name = m_name.group(1).strip()
        try:
            tpl = tm.create_template(name=name, description="Custom template")
            return {
                "type": "goal_template",
                "reply": f"✅ Custom template '{name}' created (id: {tpl.template_id}). "
                         "You can now add milestones and tasks to it.",
                "template": tpl.to_dict(),
            }
        except ValueError as e:
            return {"type": "goal_template", "reply": f"❌ {e}"}
        except Exception as e:
            return {"type": "goal_template", "reply": f"❌ Failed to create template: {e}"}

    # --- "Delete template" ---
    if re.search(r"\b(delete|remove)\s+(?:goal\s+)?template\b", text):
        m_name = re.search(r"(?:called|named|custom\s+)?(?:goal\s+)?template\s+['\"]?(.+?)['\"]?\s*$", text)
        if not m_name:
            return {"type": "goal_template", "reply": "Specify the template name to delete."}
        tpl = tm.get_template_by_name(m_name.group(1).strip())
        if not tpl:
            return {"type": "goal_template", "reply": "Template not found."}
        if tpl.is_builtin:
            return {"type": "goal_template", "reply": "❌ Built-in templates cannot be deleted."}
        try:
            tm.delete_template(tpl.template_id)
            return {"type": "goal_template", "reply": f"✅ Template '{tpl.name}' deleted."}
        except Exception as e:
            return {"type": "goal_template", "reply": f"❌ {e}"}

    return None


# ─────────────────────────────────────────────────────────────────────────────
# Unified entry point
# ─────────────────────────────────────────────────────────────────────────────

def process_goal_command(command: str) -> Optional[Dict[str, Any]]:
    """
    Main entry point for goal-related commands in the BrainV2 pipeline.

    Returns a result dict ({"type": "...", "reply": "..."}) when the command
    matches goal progress or goal template intent, or None to let the
    pipeline continue normally.
    """
    if not command or not isinstance(command, str):
        return None

    text = command.lower()

    # Try templates first (specific), then progress (general)
    # "Show goal templates" would match "goal" in progress keywords but needs template handler
    if _TEMPLATE_KEYWORDS.search(text):
        result = _handle_template(command)
        if result:
            return result

    if _PROGRESS_KEYWORDS.search(text):
        result = _handle_progress(command)
        if result:
            return result

    return None


# ─────────────────────────────────────────────────────────────────────────────
# Helper
# ─────────────────────────────────────────────────────────────────────────────

def _find_goal_by_command(command: str, goals_manager) -> Optional[Any]:
    """Find a goal matching a phrase in the command text."""
    if not goals_manager:
        return None
    # Strip common prefixes
    cleaned = re.sub(
        r"^(show|how|give|get|tell|what|list)\s+(my\s+|the\s+)?",
        "",
        command,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"\s+(goal|progress|status|report|template|summary)\s*$", "", cleaned, flags=re.IGNORECASE)
    cleaned = cleaned.strip()
    if len(cleaned) < 2:
        return None
    results = goals_manager.search_goals(cleaned)
    return results[0] if results else None


# ─────────────────────────────────────────────────────────────────────────────
# Expose canonical managers for direct access
# ─────────────────────────────────────────────────────────────────────────────

def get_goals_manager():
    return _gm()


def get_task_manager():
    return _tm()


def get_template_manager():
    return _tp()
