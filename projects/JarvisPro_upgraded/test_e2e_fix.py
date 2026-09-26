"""Quick E2E test to verify Step 6 fix."""
import sys, os, re
sys.path.insert(0, os.path.dirname(__file__))

from jarvis_core import process_goal_command, get_goals_manager, get_task_manager
from goals.manager import GoalsManager

print("=== E2E Step 6 Fix Verification ===\n")

# Step 1 -- create from template
r1 = process_goal_command("Create a coding project called Jarvis Mobile App from the Coding Project template.")
ok1 = r1 and "instantiation" in r1
print(f"[PASS] Step 1 create from template" if ok1 else f"[FAIL] Step 1 create from template: {r1}")
goal_id = r1.get("instantiation", {}).get("goal_id") if ok1 else None
if not goal_id:
    print("NO GOAL ID"); sys.exit(1)

# Step 2 -- list templates
r2 = process_goal_command("Show goal templates.")
ok2 = r2 and "templates" in str(r2)
print(f"[PASS] Step 2 list templates" if ok2 else f"[FAIL] Step 2 list templates: {r2}")

# Step 3 -- initial progress
r3 = process_goal_command("Show my goal progress")
pct3 = 0
if r3 and "goals" in r3:
    for g in r3["goals"]:
        if g.get("goal_id") == goal_id:
            pct3 = round(g.get("overall_percent", 0))
            break
print(f"[PASS] Step 3 initial 0%" if pct3 == 0 else f"[FAIL] Step 3 initial 0%: got {pct3}%")

# Step 4 -- complete one task
gm = get_goals_manager()
tm = get_task_manager()
goal = gm.get_goal(goal_id)
task_ids = goal.task_ids if goal else []
pending = [tid for tid in task_ids
           if tm.tasks[tid].state in ("created", "queued", "planning")]
if pending:
    tid = pending[0]
    tm.transition(tid, "queued")
    tm.transition(tid, "running")
    tm.transition(tid, "completed")
    print(f"[PASS] Step 4 complete task {tid[:8]}")
else:
    print("[FAIL] Step 4: no pending tasks")

# Step 5 -- reload from disk
gm2 = GoalsManager(data_dir=gm.data_dir, task_manager=tm)
goal5 = gm2.get_goal(goal_id)
t5 = tm.tasks[goal5.task_ids[0]]
ok5 = goal5 and t5.state == "completed"
print(f"[PASS] Step 5 reload from disk" if ok5 else "[FAIL] Step 5 reload from disk")

# Step 6 -- progress AFTER completing one task
r6 = process_goal_command("Show my goal progress")
pct6 = None
if r6 and "goals" in r6:
    for g in r6["goals"]:
        if g.get("goal_id") == goal_id:
            pct6 = round(g.get("overall_percent", 0))
            break
ok6 = pct6 is not None and pct6 > 0
print(f"[PASS] Step 6 progress after 1 task: {pct6}%" if ok6 else f"[FAIL] Step 6 progress after 1 task: got {pct6}%")
print(f"\nFull Step 6 result:\n{r6}")
