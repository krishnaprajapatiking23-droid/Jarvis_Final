from brains_v2.agent.task import Task


def test_task_can_be_assigned_to_manager():
    task = Task(
        goal="Build portfolio website",
        priority=8,
        confidence=90,
    )

    task.assigned_manager = "CodingManager"

    assert task.assigned_manager == "CodingManager"


def test_task_handoff_transfers_manager():
    task = Task(
        goal="Build portfolio website",
        priority=8,
        confidence=90,
    )

    task.assigned_manager = "CodingManager"

    handoff = task.handoff(
        "FileManager",
        reason="File operation required",
    )

    assert task.status == "handed_off"
    assert task.assigned_manager == "FileManager"
    assert handoff["from_manager"] == "CodingManager"
    assert handoff["to_manager"] == "FileManager"
    assert handoff["reason"] == "File operation required"


def test_task_handoff_preserves_task_information():
    task = Task(
        goal="Build portfolio website",
        steps=["Design", "Code", "Test"],
        priority=9,
        confidence=95,
        context={"project": "portfolio"},
    )

    task.assigned_manager = "CodingManager"

    original_id = task.task_id

    task.handoff(
        "TestingManager",
        reason="Testing required",
    )

    assert task.task_id == original_id
    assert task.goal == "Build portfolio website"
    assert task.steps == ["Design", "Code", "Test"]
    assert task.priority == 9
    assert task.confidence == 95
    assert task.context["project"] == "portfolio"


def test_task_handoff_history_is_recorded():
    task = Task(goal="Test application")

    task.assigned_manager = "CodingManager"

    task.handoff(
        "TestingManager",
        reason="Run tests",
    )

    assert len(task.handoff_history) == 1
    assert task.handoff_history[0]["from_manager"] == "CodingManager"
    assert task.handoff_history[0]["to_manager"] == "TestingManager"
    assert task.handoff_history[0]["reason"] == "Run tests"


def test_handoff_updates_execution_context():
    task = Task(goal="Build application")

    task.assigned_manager = "CodingManager"

    task.handoff("TestingManager")

    assert (
        task.execution_context.active_manager
        == "TestingManager"
    )