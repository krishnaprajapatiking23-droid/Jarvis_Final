from brains_v2.task_engine import TaskEngine


def test_situation_is_idle_when_no_tasks_exist():
    engine = TaskEngine()

    situation = engine.situation()

    assert situation["state"] == "idle"
    assert situation["current_task"] is None
    assert situation["task_count"] == 0


def test_situation_detects_running_task():
    engine = TaskEngine()

    engine.add("Build frontend")
    engine.start(0)

    situation = engine.situation()

    assert situation["state"] == "running"
    assert situation["current_task"]["task"] == "Build frontend"
    assert situation["current_task"]["running"] is True


def test_situation_detects_failed_task_and_error():
    engine = TaskEngine()

    engine.add("Build backend")
    engine.start(0)
    engine.fail(0, "Database connection failed")

    situation = engine.situation()

    assert situation["state"] == "failed"
    assert situation["current_task"]["task"] == "Build backend"
    assert situation["current_task"]["error"] == "Database connection failed"
    assert situation["failed_count"] == 1


def test_situation_detects_completed_task_and_result():
    engine = TaskEngine()

    engine.add("Run tests")
    engine.start(0)
    engine.complete(0, result="All tests passed")

    situation = engine.situation()

    assert situation["state"] == "completed"
    assert situation["current_task"]["task"] == "Run tests"
    assert situation["completed_count"] == 1
    assert situation["last_result"] == "All tests passed"