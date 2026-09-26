"""
Goal Features Test Suite - Phase 15 Feature A (Progress Reports) + Feature B (Templates).

Tests 1-7:   Goal Progress Reports
Tests 8-13:  Goal Templates
Test  14:    End-to-end integration
Test  15:    Transaction failure / integrity

Run from project root:
    python goal_features_test.py
"""

from __future__ import annotations

import os
import sys
import shutil
import tempfile
import unittest
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ── prepend project root to path ────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))

# ── isolated data dirs ───────────────────────────────────────────────────────
_goal_tempdir = tempfile.mkdtemp(prefix="goals_test_")
_task_tempdir = tempfile.mkdtemp(prefix="tasks_test_")


# ── helpers ──────────────────────────────────────────────────────────────────

def fresh_goals_manager(tempdir: str) -> "GoalsManager":
    """Create a GoalsManager with a fresh temp data dir and its own TaskManager."""
    from goals.manager import GoalsManager
    from jarvis_core.tasks import TaskManager, TaskStore
    db_path = os.path.join(tempdir, "goals.db")
    task_mgr = TaskManager(store=TaskStore(db_path=db_path))
    gm = GoalsManager(data_dir=tempdir, task_manager=task_mgr)
    return gm


def fresh_task_manager(tempdir: str):
    """Create a TaskManager with a fresh temp data dir."""
    from jarvis_core.tasks import TaskManager, TaskStore
    db_path = os.path.join(tempdir, "goals.db")
    return TaskManager(store=TaskStore(db_path=db_path))


def fresh_template_manager(tempdir: str):
    """Create a GoalTemplateManager with a fresh temp data dir."""
    from jarvis_core.goal_templates import GoalTemplateManager
    return GoalTemplateManager(data_dir=tempdir)


class MockTask:
    """Minimal mock task for testing goal_progress without real TaskManager."""
    def __init__(self, task_id, title, state, depends_on=None, priority=5,
                 failure_reason=None, created_at=None):
        self.task_id = task_id
        self.title = title
        self.state = state
        self.depends_on = depends_on or []
        self.priority = priority
        self.failure_reason = failure_reason
        self.created_at = created_at or datetime.now(timezone.utc).isoformat()
        self.progress = 0.0


class MockTaskManager:
    """Fake TaskManager that returns predefined tasks."""
    def __init__(self, tasks: dict):
        # tasks: {task_id: MockTask}
        self._task_map = {tid: t for tid, t in tasks.items()}
        # Expose .tasks for code that accesses it directly (e.g. dict iteration)
        self.tasks = self._task_map

    def get(self, task_id):
        if task_id not in self._task_map:
            raise KeyError(task_id)
        return self._task_map[task_id]


# ── Import after path is set ───────────────────────────────────────────────────
from goals.models import Goal, Milestone, Priority, GoalCategory, GoalStatus
from jarvis_core.goal_progress import (
    calculate_goal_progress,
    detect_blockers,
    deadline_status,
    next_recommended_action,
    generate_goal_report,
    get_goal_progress,
    get_goal_summary,
    get_milestone_progress,
    get_goal_task_breakdown,
)
from jarvis_core.goal_templates import (
    GoalTemplateManager,
    get_template_manager,
    _get_builtin_templates,
)


# ═══════════════════════════════════════════════════════════════════════════════
# TESTS 1–7: Goal Progress Reports
# ═══════════════════════════════════════════════════════════════════════════════

class TestProgressEmptyGoal(unittest.TestCase):
    """Test 1 — Empty goal (no milestones, no tasks)."""

    def test_empty_goal_zero_progress(self):
        goal = Goal(id="g_empty", title="Empty Goal")
        result = calculate_goal_progress(goal)
        self.assertEqual(result["overall_progress"], 0.0)
        self.assertEqual(result["calculation"], "no_goal")
        self.assertEqual(result["task_summary"]["total"], 0)


class TestProgressOneTask(unittest.TestCase):
    """Test 2 — One milestone with one task: 1 completed → 100%."""

    def test_one_completed_task(self):
        goal = Goal(
            id="g_one",
            title="One Task Goal",
            milestones=[
                Milestone(id="m1", title="M1", task_id="t1", completed=False),
            ],
        )
        mock_tm = MockTaskManager({
            "t1": MockTask("t1", "Task 1", "completed"),
        })
        result = calculate_goal_progress(goal, mock_tm)
        self.assertEqual(result["overall_progress"], 1.0)
        self.assertEqual(result["task_summary"]["completed"], 1)
        self.assertEqual(result["task_summary"]["total"], 1)


class TestProgressMixedStates(unittest.TestCase):
    """Test 3 — Mixed task states. FAILED/CANCELLED/ROLLED_BACK must NOT count."""

    def test_failed_not_completed(self):
        goal = Goal(
            id="g_mixed",
            title="Mixed States",
            milestones=[
                Milestone(id="m1", title="Done", task_id="t1"),
                Milestone(id="m2", title="Failed", task_id="t2"),
                Milestone(id="m3", title="Running", task_id="t3"),
                Milestone(id="m4", title="Pending", task_id="t4"),
                Milestone(id="m5", title="Cancelled", task_id="t5"),
            ],
        )
        mock_tm = MockTaskManager({
            "t1": MockTask("t1", "Done", "completed"),
            "t2": MockTask("t2", "Failed", "failed", failure_reason="out of memory"),
            "t3": MockTask("t3", "Running", "running"),
            "t4": MockTask("t4", "Pending", "queued"),
            "t5": MockTask("t5", "Cancelled", "cancelled"),
        })
        result = calculate_goal_progress(goal, mock_tm)
        # Only t1 (completed) counts as done → 1/5 = 20%
        self.assertAlmostEqual(result["overall_progress"], 0.2, places=2)
        self.assertEqual(result["task_summary"]["completed"], 1)
        self.assertEqual(result["task_summary"]["blocked"], 2)   # failed + cancelled
        self.assertEqual(result["task_summary"]["running"], 1)
        self.assertEqual(result["task_summary"]["pending"], 1)

    def test_rolled_back_not_completed(self):
        goal = Goal(
            id="g_rb",
            title="Rolled Back",
            milestones=[Milestone(id="m1", title="RB", task_id="t1")],
        )
        mock_tm = MockTaskManager({
            "t1": MockTask("t1", "Rolled Back", "rolled_back"),
        })
        result = calculate_goal_progress(goal, mock_tm)
        self.assertEqual(result["overall_progress"], 0.0)
        self.assertEqual(result["task_summary"]["blocked"], 1)


class TestProgressMilestones(unittest.TestCase):
    """Test 4 — Multiple milestones with different task counts."""

    def test_milestone_weighted_progress(self):
        goal = Goal(
            id="g_ms",
            title="Multi-Milestone",
            milestones=[
                Milestone(id="m1", title="MS1", task_id="t1"),  # 1/1 = 100%
                Milestone(id="m2", title="MS2", task_id="t2"),  # 0/1 = 0%
                Milestone(id="m3", title="MS3", task_id="t3"),  # 0/1 = 0%
            ],
        )
        mock_tm = MockTaskManager({
            "t1": MockTask("t1", "Done", "completed"),
            "t2": MockTask("t2", "Pending", "queued"),
            "t3": MockTask("t3", "Running", "running"),
        })
        result = calculate_goal_progress(goal, mock_tm)
        # (1.0 + 0.0 + 0.0) / 3 = 33.33%
        self.assertAlmostEqual(result["overall_progress"], 1.0 / 3.0, places=2)


class TestProgressBlockers(unittest.TestCase):
    """Test 5 — Failed dependency marks task as blocked."""

    def test_failed_dependency_blocks(self):
        goal = Goal(
            id="g_dep",
            title="Dependency Test",
            milestones=[
                Milestone(id="m1", title="Task B Milestone", task_id="tB"),
            ],
        )
        mock_tm = MockTaskManager({
            "tA": MockTask("tA", "Task A", "failed"),
            "tB": MockTask("tB", "Task B", "running", depends_on=["tA"]),
        })
        blockers = detect_blockers(goal, mock_tm)
        self.assertEqual(len(blockers), 1)
        self.assertEqual(blockers[0]["type"], "failed_dependency")
        self.assertEqual(blockers[0]["affected_task_id"], "tB")
        self.assertEqual(blockers[0]["dependency_task_id"], "tA")


class TestProgressDeadline(unittest.TestCase):
    """Test 6 — Deadline analysis."""

    def test_on_track(self):
        goal = Goal(
            id="g_dl",
            title="Deadline Test",
            deadline=datetime.now(timezone.utc) + timedelta(days=5),
        )
        result = deadline_status(goal)
        self.assertEqual(result["status"], "ON_TRACK")
        self.assertTrue(result["has_deadline"])

    def test_at_risk(self):
        goal = Goal(
            id="g_ar",
            title="At Risk",
            deadline=datetime.now(timezone.utc) + timedelta(hours=12),
        )
        result = deadline_status(goal)
        self.assertEqual(result["status"], "AT_RISK")

    def test_overdue(self):
        goal = Goal(
            id="g_ov",
            title="Overdue",
            deadline=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        result = deadline_status(goal)
        self.assertEqual(result["status"], "OVERDUE")

    def test_no_deadline(self):
        goal = Goal(id="g_nd", title="No Deadline")
        result = deadline_status(goal)
        self.assertEqual(result["status"], "NO_DEADLINE")
        self.assertFalse(result["has_deadline"])


class TestProgressPersistence(unittest.TestCase):
    """Test 7 — Progress consistent across save/load cycles."""

    def test_persist_and_reload_same_progress(self):
        tdir = tempfile.mkdtemp(prefix="persist_test_")
        try:
            gm = fresh_goals_manager(tdir)
            goal = gm.create_goal(title="Persist Test")
            gm.add_milestone(goal.id, "MS1")
            gm.add_milestone(goal.id, "MS2")
            # Mark one milestone complete
            ms_id = goal.milestones[0].id
            gm.complete_milestone(goal.id, ms_id)
            # Reload
            gm2 = fresh_goals_manager(tdir)
            reloaded = gm2.get_goal(goal.id)
            self.assertIsNotNone(reloaded)
            # Progress should be 50% (1 of 2 milestones)
            result = calculate_goal_progress(reloaded)
            self.assertAlmostEqual(result["overall_progress"], 0.5, places=2)
        finally:
            shutil.rmtree(tdir, ignore_errors=True)


# ═══════════════════════════════════════════════════════════════════════════════
# TESTS 8–13: Goal Templates
# ═══════════════════════════════════════════════════════════════════════════════

class TestTemplateListBuiltins(unittest.TestCase):
    """Test 8 — All 5 built-in templates are present."""

    def test_five_builtin_templates(self):
        tdir = tempfile.mkdtemp(prefix="tpl_builtins_")
        try:
            tm = fresh_template_manager(tdir)
            templates = tm.list_templates()
            builtin = [t for t in templates if t.is_builtin]
            self.assertEqual(len(builtin), 5)
            names = {t.name for t in builtin}
            self.assertIn("Coding Project", names)
            self.assertIn("Research Project", names)
            self.assertIn("Study Project", names)
            self.assertIn("Business Project", names)
            self.assertIn("Personal Project", names)
        finally:
            shutil.rmtree(tdir, ignore_errors=True)

    def test_coding_template_has_4_milestones(self):
        tdir = tempfile.mkdtemp(prefix="tpl_coding_")
        try:
            tm = fresh_template_manager(tdir)
            tpl = tm.get_template_by_name("Coding Project")
            self.assertIsNotNone(tpl)
            self.assertEqual(len(tpl.milestones), 4)
            milestone_names = {ms["title"] for ms in tpl.milestones}
            self.assertIn("Planning", milestone_names)
            self.assertIn("Implementation", milestone_names)
            self.assertIn("Testing", milestone_names)
            self.assertIn("Release", milestone_names)
        finally:
            shutil.rmtree(tdir, ignore_errors=True)


class TestTemplateInstantiation(unittest.TestCase):
    """Test 9 — Template instantiation creates real Goal/Milestones/Tasks."""

    def test_instantiate_coding_template(self):
        tdir = tempfile.mkdtemp(prefix="tpl_inst_")
        try:
            gm = fresh_goals_manager(tdir)
            tm = fresh_template_manager(tdir)

            result = tm.instantiate(
                template_id="tpl_coding_v1",
                goals_manager=gm,
                variables={"project_name": "Jarvis Mobile App"},
            )

            self.assertIsNone(result.get("error"))
            self.assertIsNotNone(result.get("goal_id"))
            self.assertEqual(result["milestones_created"], 4)
            self.assertGreater(result["tasks_created"], 0)
            self.assertEqual(result["template_id"], "tpl_coding_v1")
            self.assertEqual(result["template_version"], 1)

            # Verify goal exists in GoalsManager
            goal = gm.get_goal(result["goal_id"])
            self.assertIsNotNone(goal)
            self.assertEqual(goal.title, "Jarvis Mobile App")
            self.assertEqual(len(goal.milestones), 4)
            self.assertEqual(goal.metadata.get("template_id"), "tpl_coding_v1")
            self.assertEqual(goal.metadata.get("template_version"), 1)

        finally:
            shutil.rmtree(tdir, ignore_errors=True)


class TestTemplateProvenance(unittest.TestCase):
    """Test 10 — Template provenance stored in goal metadata."""

    def test_provenance_fields(self):
        tdir = tempfile.mkdtemp(prefix="tpl_prov_")
        try:
            gm = fresh_goals_manager(tdir)
            tm = fresh_template_manager(tdir)

            result = tm.instantiate(
                template_id="tpl_study_v1",
                goals_manager=gm,
                variables={"project_name": "Learn Rust"},
            )

            goal = gm.get_goal(result["goal_id"])
            self.assertEqual(goal.metadata.get("template_id"), "tpl_study_v1")
            self.assertEqual(goal.metadata.get("template_name"), "Study Project")
            self.assertIn("instantiated_at", goal.metadata)
            self.assertIn("instantiated_by", goal.metadata)

        finally:
            shutil.rmtree(tdir, ignore_errors=True)


class TestTemplateCustom(unittest.TestCase):
    """Test 11 — Custom template CRUD."""

    def test_create_custom_template(self):
        tdir = tempfile.mkdtemp(prefix="tpl_custom_")
        try:
            tm = fresh_template_manager(tdir)
            tpl = tm.create_template(
                name="My App Project",
                description="My custom app template",
                milestones=[
                    {"title": "Design", "tasks": [{"title": "Sketch UI", "priority": 2, "depends_on": []}]},
                    {"title": "Build", "tasks": [{"title": "Implement UI", "priority": 2, "depends_on": []}]},
                ],
            )
            self.assertFalse(tpl.is_builtin)
            self.assertEqual(tpl.name, "My App Project")
            self.assertEqual(len(tpl.milestones), 2)

            # Verify persistence
            tm2 = fresh_template_manager(tdir)
            loaded = tm2.get_template(tpl.template_id)
            self.assertIsNotNone(loaded)
            self.assertEqual(loaded.name, "My App Project")

            # Update
            updated = tm.update_template(tpl.template_id, description="Updated description")
            self.assertEqual(updated.version, 2)

            # Delete
            deleted = tm.delete_template(tpl.template_id)
            self.assertTrue(deleted)
            self.assertIsNone(tm.get_template(tpl.template_id))

        finally:
            shutil.rmtree(tdir, ignore_errors=True)

    def test_cannot_delete_builtin(self):
        tdir = tempfile.mkdtemp(prefix="tpl_del_builtin_")
        try:
            tm = fresh_template_manager(tdir)
            with self.assertRaises(ValueError) as ctx:
                tm.delete_template("tpl_coding_v1")
            self.assertIn("cannot be deleted", str(ctx.exception))
        finally:
            shutil.rmtree(tdir, ignore_errors=True)


# ═══════════════════════════════════════════════════════════════════════════════
# TEST 12: Transaction Failure / Integrity
# ═══════════════════════════════════════════════════════════════════════════════

class TestTransactionIntegrity(unittest.TestCase):
    """Test 12 — Failed instantiation leaves no partial goal."""

    def test_no_partial_goal_on_failure(self):
        tdir = tempfile.mkdtemp(prefix="tpl_txn_")
        try:
            gm = fresh_goals_manager(tdir)
            tm = fresh_template_manager(tdir)

            # Instantiate a valid template
            result = tm.instantiate(
                template_id="tpl_coding_v1",
                goals_manager=gm,
                variables={"project_name": "Valid Goal"},
            )
            goal_id = result["goal_id"]

            # Instantiate an INVALID template id — should return error, no goal
            result_bad = tm.instantiate(
                template_id="tpl_nonexistent_xyz",
                goals_manager=gm,
                variables={"project_name": "Bad Goal"},
            )
            self.assertIsNotNone(result_bad.get("error"))
            self.assertIsNone(result_bad.get("goal_id"))

            # The valid goal should still exist
            self.assertIsNotNone(gm.get_goal(goal_id))
            # No extra goals should have been created
            all_goals = gm.get_all_goals()
            self.assertEqual(len(all_goals), 1)

        finally:
            shutil.rmtree(tdir, ignore_errors=True)


# ═══════════════════════════════════════════════════════════════════════════════
# TEST 13: End-to-End Integration
# ═══════════════════════════════════════════════════════════════════════════════

class TestEndToEnd(unittest.TestCase):
    """Test 13 — Full E2E: Create from template → check progress → complete one task → recheck."""

    def test_full_e2e_workflow(self):
        tdir = tempfile.mkdtemp(prefix="e2e_")
        try:
            # ── Setup ──────────────────────────────────────────────────────────
            # Share a single TaskManager across GoalsManager and TemplateManager
            # so tasks created during instantiate() are visible here.
            from jarvis_core.tasks import TaskManager, TaskStore
            db_path = os.path.join(tdir, "goals.db")
            shared_tm = TaskManager(store=TaskStore(db_path=db_path))
            from goals.manager import GoalsManager
            gm = GoalsManager(data_dir=tdir, task_manager=shared_tm)
            tm = GoalTemplateManager(data_dir=tdir)
            # Ensure the template manager uses the same TaskManager
            tm._task_manager = shared_tm

            # ── Step 1: Instantiate from template ─────────────────────────────
            result = tm.instantiate(
                template_id="tpl_coding_v1",
                goals_manager=gm,
                variables={"project_name": "Jarvis Mobile App"},
            )
            self.assertIsNone(result.get("error"))
            goal_id = result["goal_id"]
            self.assertEqual(result["milestones_created"], 4)

            # ── Step 2: Get initial progress ───────────────────────────────────
            goal = gm.get_goal(goal_id)
            from jarvis_core.goal_progress import calculate_goal_progress

            progress_before = calculate_goal_progress(goal)
            self.assertEqual(progress_before["overall_progress"], 0.0)  # nothing done

            # ── Step 3: Complete the first task (Define project requirements) ─
            # The "Planning" milestone's first task
            first_task_id = None
            for ms in goal.milestones:
                if ms.task_id:
                    first_task_id = ms.task_id
                    break

            self.assertIsNotNone(first_task_id, "Expected at least one task to exist")

            # Manually set task to completed via TaskManager
            # Tasks start in CREATED state; must transition CREATED→QUEUED→RUNNING→COMPLETED
            # (QUEUED→COMPLETED is not a valid transition; must go through RUNNING)
            real_tm = fresh_task_manager(tdir)
            linked_task_ids = list(goal.task_ids)
            if linked_task_ids:
                try:
                    real_tm.transition(linked_task_ids[0], "queued")
                    real_tm.transition(linked_task_ids[0], "running")
                    real_tm.transition(linked_task_ids[0], "completed")
                except Exception:
                    pass

            # Re-calculate progress with real task manager
            progress_after = calculate_goal_progress(goal, real_tm)
            # Planning milestone has 3 tasks; first one done → 1/3 for that milestone
            # Overall = (1/3) / 4 milestones ≈ 0.083
            self.assertGreater(progress_after["overall_progress"], 0.0)

            # ── Step 4: Verify goal still exists and has correct metadata ───────
            reloaded = gm.get_goal(goal_id)
            self.assertIsNotNone(reloaded)
            self.assertEqual(reloaded.metadata.get("template_id"), "tpl_coding_v1")
            self.assertEqual(reloaded.metadata.get("template_name"), "Coding Project")

            print(f"\n[E2E] Initial progress: {progress_before['overall_progress']}")
            print(f"[E2E] After 1 task:     {progress_after['overall_progress']}")
            print(f"[E2E] Goal milestones:  {len(reloaded.milestones)}")
            print("[E2E] Template provenance confirmed [OK]")

        finally:
            shutil.rmtree(tdir, ignore_errors=True)


# ═══════════════════════════════════════════════════════════════════════════════
# TEST 14: Command Handler Integration
# ═══════════════════════════════════════════════════════════════════════════════

class TestCommandHandler(unittest.TestCase):
    """Test 14 — process_goal_command routes correctly."""

    def test_progress_keyword_routes(self):
        from jarvis_core import process_goal_command

        # No match
        result = process_goal_command("Hello, how are you?")
        self.assertIsNone(result)

    def test_progress_command(self):
        from jarvis_core import process_goal_command
        tdir = tempfile.mkdtemp(prefix="cmd_test_")
        try:
            gm = fresh_goals_manager(tdir)
            tm = fresh_template_manager(tdir)

            # Create a goal
            goal = gm.create_goal(title="My Test Goal")

            # Monkey-patch _gm to return our test manager
            import jarvis_core
            old_gm = jarvis_core._goals_manager
            jarvis_core._goals_manager = gm
            old_tm = jarvis_core._task_manager
            jarvis_core._task_manager = None

            try:
                result = process_goal_command("Show my goal progress")
                self.assertIsNotNone(result)
                self.assertEqual(result["type"], "goal_progress")
                self.assertIn("reply", result)
            finally:
                jarvis_core._goals_manager = old_gm
                jarvis_core._task_manager = old_tm

        finally:
            shutil.rmtree(tdir, ignore_errors=True)

    def test_template_list_command(self):
        from jarvis_core import process_goal_command
        tdir = tempfile.mkdtemp(prefix="tpl_cmd_")
        try:
            import jarvis_core
            old_tp = jarvis_core._template_manager
            jarvis_core._template_manager = None
            try:
                result = process_goal_command("Show goal templates")
                self.assertIsNotNone(result)
                self.assertEqual(result["type"], "goal_template")
                self.assertIn("reply", result)
                self.assertIn("Coding Project", result["reply"])
            finally:
                jarvis_core._template_manager = old_tp
        finally:
            shutil.rmtree(tdir, ignore_errors=True)


# ═══════════════════════════════════════════════════════════════════════════════
# TEST 15: Next Recommended Action
# ═══════════════════════════════════════════════════════════════════════════════

class TestNextAction(unittest.TestCase):
    """Test 15 — next_recommended_action returns correct task."""

    def test_returns_ready_task(self):
        goal = Goal(
            id="g_next",
            title="Next Action Test",
            milestones=[
                Milestone(id="m1", title="Ready", task_id="t_ready"),
                Milestone(id="m2", title="Blocked", task_id="t_blocked"),
            ],
        )
        mock_tm = MockTaskManager({
            "t_ready":   MockTask("t_ready", "Ready Task", "created", depends_on=[], priority=1),
            "t_blocked": MockTask("t_blocked", "Blocked Task", "running", depends_on=["tA"]),
        })
        action = next_recommended_action(goal, mock_tm)
        self.assertIsNotNone(action)
        self.assertEqual(action["task_id"], "t_ready")
        self.assertEqual(action["action"], "start")

    def test_none_when_all_blocked(self):
        goal = Goal(
            id="g_blocked",
            title="All Blocked",
            milestones=[Milestone(id="m1", title="Blocked", task_id="t1")],
        )
        mock_tm = MockTaskManager({
            "t1": MockTask("t1", "Task", "failed", depends_on=["tA"]),
        })
        action = next_recommended_action(goal, mock_tm)
        self.assertIsNone(action)


# ═══════════════════════════════════════════════════════════════════════════════
# Run
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 60)
    print("JARVIS PRO — Goal Features Test Suite")
    print("Features A: Goal Progress Reports | B: Goal Templates")
    print("=" * 60)

    # Clean up stale temp dirs from previous runs
    for _d in [_goal_tempdir, _task_tempdir]:
        shutil.rmtree(_d, ignore_errors=True)

    unittest.main(verbosity=2)
