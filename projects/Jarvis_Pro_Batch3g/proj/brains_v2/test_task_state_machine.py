from brains_v2.agent.task import Task


def test_task_starts_in_pending_state():
    task = Task(goal="Build application")

    assert task.status == "pending"


def test_valid_task_lifecycle():
    task = Task(goal="Build application")

    task.start()
    assert task.status == "running"

    task.complete("Build successful")
    assert task.status == "completed"
    assert task.result == "Build successful"


def test_failed_task_can_be_replanned():
    task = Task(goal="Build application")

    task.start()
    task.fail("Build failed")

    assert task.status == "failed"
    assert task.error == "Build failed"

    task.replan()

    assert task.status == "replanned"


def test_replanned_task_can_run_again():
    task = Task(goal="Build application")

    task.start()
    task.fail("Build failed")
    task.replan()
    task.start()

    assert task.status == "running"


def test_invalid_transition_is_rejected():
    task = Task(goal="Build application")

    try:
        task.complete("Should not work")
    except ValueError:
        pass
    else:
        raise AssertionError(
            "Invalid transition should raise ValueError"
        )


def test_completed_task_is_finished():
    task = Task(goal="Build application")

    task.start()
    task.complete("Success")

    assert task.is_finished() is True
    assert task.is_failed() is False