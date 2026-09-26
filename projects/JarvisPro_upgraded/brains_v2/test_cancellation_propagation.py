from brains_v2.agent.task import Task, TaskEngine


def test_parent_can_have_child_tasks():
    engine = TaskEngine()

    parent = Task(
        goal="Build application"
    )

    child = Task(
        goal="Build frontend"
    )

    engine.add(parent)
    engine.add_child_task(parent, child)

    assert child.parent_task_id == parent.task_id
    assert child.task_id in parent.child_task_ids


def test_cancelling_parent_cancels_children():
    engine = TaskEngine()

    parent = Task(
        goal="Build application"
    )

    child_one = Task(
        goal="Build frontend"
    )

    child_two = Task(
        goal="Build backend"
    )

    engine.add(parent)
    engine.add_child_task(parent, child_one)
    engine.add_child_task(parent, child_two)

    cancelled = engine.cancel_task(
        parent.task_id,
        reason="User cancelled project",
    )

    assert parent.status == "cancelled"
    assert child_one.status == "cancelled"
    assert child_two.status == "cancelled"

    assert parent.task_id in cancelled
    assert child_one.task_id in cancelled
    assert child_two.task_id in cancelled


def test_cancellation_propagates_to_nested_children():
    engine = TaskEngine()

    parent = Task(
        goal="Build application"
    )

    child = Task(
        goal="Build frontend"
    )

    grandchild = Task(
        goal="Create frontend files"
    )

    engine.add(parent)
    engine.add_child_task(parent, child)
    engine.add_child_task(child, grandchild)

    cancelled = engine.cancel_task(
        parent.task_id
    )

    assert parent.status == "cancelled"
    assert child.status == "cancelled"
    assert grandchild.status == "cancelled"

    assert len(cancelled) == 3


def test_completed_child_is_not_cancelled():
    engine = TaskEngine()

    parent = Task(
        goal="Build application"
    )

    child = Task(
        goal="Build frontend"
    )

    engine.add(parent)
    engine.add_child_task(parent, child)

    child.start()
    child.complete("Frontend complete")

    cancelled = engine.cancel_task(
        parent.task_id
    )

    assert parent.status == "cancelled"
    assert child.status == "completed"
    assert child.task_id not in cancelled


def test_cancellation_reason_is_propagated():
    engine = TaskEngine()

    parent = Task(
        goal="Build application"
    )

    child = Task(
        goal="Build frontend"
    )

    engine.add(parent)
    engine.add_child_task(parent, child)

    reason = "User stopped the task"

    engine.cancel_task(
        parent.task_id,
        reason=reason,
    )

    assert parent.error == reason
    assert child.error == reason


def test_missing_task_returns_empty_cancellation_list():
    engine = TaskEngine()

    result = engine.cancel_task(
        "non-existent-task"
    )

    assert result == []