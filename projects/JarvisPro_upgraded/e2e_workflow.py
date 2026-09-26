"""E2E workflow test for Goal Progress Reports + Goal Templates."""
import tempfile, os, sys, shutil, io
from pathlib import Path

# Fix Unicode output on Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))

print("=" * 60)
print("E2E WORKFLOW — Goal Progress Reports + Goal Templates")
print("=" * 60)

tdir = tempfile.mkdtemp(prefix="e2e_")
print(f"\nTemp dir: {tdir}")

try:
    # 1. Load the real command pipeline
    from jarvis_core import process_goal_command
    print("\n[Step 1] Command pipeline loaded OK")

    # 2. Create shared TaskManager + GoalsManager (real setup)
    from jarvis_core.tasks import TaskManager, TaskStore
    from goals.manager import GoalsManager
    from jarvis_core.goal_templates import GoalTemplateManager

    db_path = os.path.join(tdir, "goals.db")
    shared_tm = TaskManager(store=TaskStore(db_path=db_path))
    gm = GoalsManager(data_dir=tdir, task_manager=shared_tm)
    tm = GoalTemplateManager(data_dir=tdir)
    tm._task_manager = shared_tm

    # Inject into jarvis_core singletons
    import jarvis_core
    old_gm = jarvis_core._goals_manager
    old_tm = jarvis_core._task_manager
    old_tp = jarvis_core._template_manager
    jarvis_core._goals_manager = gm
    jarvis_core._task_manager = shared_tm
    jarvis_core._template_manager = tm

    try:
        # 3. Command: Show goal templates
        print("\n[Step 2] Command: Show goal templates")
        r = process_goal_command("Show goal templates")
        print(f"  Type: {r.get('type')}")
        assert r["type"] == "goal_template", f"FAIL: got {r['type']}"
        assert "Coding Project" in r["reply"]
        print(f"  Reply preview: {r['reply'][:80]}...")
        print("  PASS: Template listing works")

        # 4. Command: Create goal from template
        print("\n[Step 3] Command: Create a Jarvis Mobile App goal from the Coding Project template")
        r2 = process_goal_command(
            "Create a Jarvis Mobile App goal from the Coding Project template"
        )
        print(f"  Type: {r2.get('type')}")
        print(f"  Keys: {list(r2.keys())}")
        if "instantiation" in r2:
            inst = r2.get("instantiation", {})
            goal_id = inst.get("goal_id")
            inst_error = inst.get("error")
            print(f"  inst keys: {list(inst.keys())}")
            if inst_error:
                print(f"  INSTANTIATION ERROR: {inst_error}")
                # Try to extract goal_id from reply via regex
                import re
                m = re.search(r"id[:\s]+([a-f0-9-]{36})", str(r2.get("reply", "")))
                if m:
                    goal_id = m.group(1)
                    print(f"  Found goal_id in reply: {goal_id}")
        elif "goal_id" in r2:
            goal_id = r2.get("goal_id")
        else:
            goal_id = None
        print(f"  Reply: {str(r2.get('reply',''))[:300]}")
        assert goal_id, f"No goal_id returned. Full response: {r2}"
        print(f"  Goal ID: {goal_id}")
        print(f"  Milestones: {inst.get('milestones_created')}")
        print(f"  Tasks: {inst.get('tasks_created')}")
        print("  PASS: Template instantiation works")

        # 5. Command: Show goal progress (before any work)
        print("\n[Step 4] Command: Show my goal progress")
        r3 = process_goal_command("Show my goal progress")
        print(f"  Type: {r3.get('type')}")
        assert r3["type"] == "goal_progress", f"FAIL: got {r3['type']}"
        pct = r3.get("report", {}).get("overall_percent", 0)
        print(f"  Overall: {pct}%")
        print("  PASS: Progress reporting works")

        # 6. Complete one task and recheck
        print("\n[Step 5] Completing first task via TaskManager...")
        goal = gm.get_goal(goal_id)
        first_task = list(goal.task_ids)[0]
        shared_tm.transition(first_task, "queued")
        shared_tm.transition(first_task, "running")
        shared_tm.transition(first_task, "completed")
        task = shared_tm.get(first_task)
        print(f"  Task state: {task.state}")
        assert task.state == "completed"

        # Reload goal (persistence check)
        gm2 = GoalsManager(data_dir=tdir, task_manager=shared_tm)
        goal2 = gm2.get_goal(goal_id)
        print(f"  Reloaded goal milestones: {len(goal2.milestones)}")
        print(f"  Reloaded task_ids: {len(goal2.task_ids)}")
        print("  PASS: Goal reload works")

        # 7. Recheck progress
        print("\n[Step 6] Command: Show my goal progress (after completing one task)")

        # Deep debug: trace exact IDs
        from jarvis_core import _gm, _tm
        debug_gm = _gm()
        debug_tm = debug_gm._task_manager if (debug_gm and debug_gm._task_manager) else _tm()
        print(f"  DEBUG: gm._task_manager={debug_tm}")
        if debug_tm:
            all_tids = list(debug_tm.tasks.keys())
            print(f"  DEBUG: all TM task_ids ({len(all_tids)}): {all_tids}")
            all_states = [(tid, debug_tm.tasks[tid].state) for tid in all_tids]
            print(f"  DEBUG: task states: {all_states}")
        print(f"  DEBUG: goal2.task_ids: {goal2.task_ids}")
        print(f"  DEBUG: milestone task_ids: {[m.task_id for m in goal2.milestones]}")
        if debug_tm:
            # Check if milestone task_id exists in TM
            for m in goal2.milestones:
                exists = m.task_id in debug_tm.tasks if m.task_id else False
                print(f"  DEBUG: m.task_id={m.task_id} in TM? {exists}")


        r4 = process_goal_command("Show my goal progress")
        pct2 = r4.get("report", {}).get("overall_percent", 0)
        print(f"  Overall: {pct2}%")
        assert pct2 > 0, f"FAIL: progress still 0 after completing task"
        print("  PASS: Progress updated after completing task")

        print("\n" + "=" * 60)
        print("E2E WORKFLOW COMPLETE -- ALL STEPS PASSED")
        print("=" * 60)

    finally:
        jarvis_core._goals_manager = old_gm
        jarvis_core._task_manager = old_tm
        jarvis_core._template_manager = old_tp

finally:
    shutil.rmtree(tdir, ignore_errors=True)
    print(f"\nCleaned up: {tdir}")
