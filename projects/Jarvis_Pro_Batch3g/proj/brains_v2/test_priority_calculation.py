from brains_v2.task_queue import TaskQueue


def test_higher_priority_task_runs_first():
    queue = TaskQueue()

    queue.add("Low priority task", priority=2)
    queue.add("High priority task", priority=9)

    first = queue.next()

    assert first["task"] == "High priority task"
    assert first["priority"] == 9


def test_priority_is_limited_to_valid_range():
    queue = TaskQueue()

    queue.add("Too high", priority=20)
    queue.add("Too low", priority=-5)

    tasks = queue.all()

    priorities = {
        task["task"]: task["priority"]
        for task in tasks
    }

    assert priorities["Too high"] == 10
    assert priorities["Too low"] == 1


def test_prioritize_changes_execution_order():
    queue = TaskQueue()

    queue.add("Task A", priority=3)
    queue.add("Task B", priority=5)

    queue.prioritize("Task A", priority=10)

    first = queue.next()

    assert first["task"] == "Task A"
    assert first["priority"] == 10