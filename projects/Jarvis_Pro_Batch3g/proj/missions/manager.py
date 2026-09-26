from missions.planner import create_mission
from missions.executor import execute_task
from missions.report import create_report
from missions.history import save_mission


def mission_manager(goal):

    save_mission(goal)

    tasks = create_mission(goal)

    results = {}

    for task in tasks:

        print(f"Executing: {task}")

        results[task] = execute_task(task, goal)

    return create_report(results)