from brains_v2.agent.task import Task


def test_unified_task_contains_core_fields():
    task = Task(
        goal="Build a website",
        steps=["Design", "Frontend", "Testing"],
        priority=8,
        confidence=95,
        context={"project": "portfolio"}
    )

    assert task.task_id
    assert task.goal == "Build a website"
    assert task.steps == ["Design", "Frontend", "Testing"]
    assert task.priority == 8
    assert task.confidence == 95
    assert task.status == "pending"
    assert task.context["project"] == "portfolio"
    assert task.result is None
    assert task.error is None


def test_unified_task_tracks_lifecycle():
    task = Task(goal="Run tests")

    assert task.status == "pending"

    task.start()
    assert task.status == "running"

    task.complete("All tests passed")
    assert task.status == "completed"
    assert task.result == "All tests passed"
    assert task.is_finished() is True


def test_unified_task_tracks_failure():
    task = Task(goal="Build application")

    task.start()
    task.fail("Build failed")

    assert task.status == "failed"
    assert task.error == "Build failed"
    assert task.is_finished() is True


def test_unified_task_can_be_serialized():
    task = Task(
        goal="Create app",
        priority=9,
        confidence=90
    )

    data = task.to_dict()

    assert isinstance(data, dict)
    assert data["task_id"] == task.task_id
    assert data["goal"] == "Create app"
    assert data["priority"] == 9
    assert data["confidence"] == 90
    assert data["status"] == "pending"