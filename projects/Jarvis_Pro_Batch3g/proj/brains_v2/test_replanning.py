from brains_v2.task_engine import TaskEngine


def test_task_failure_is_recorded():
    engine = TaskEngine()

    engine.add("Build frontend")
    engine.fail(0, "Build failed")

    assert len(engine.failed()) == 1
    assert engine.failed()[0]["task"] == "Build frontend"
    assert engine.failed()[0]["error"] == "Build failed"


def test_replanning_creates_alternative_after_failure():
    engine = TaskEngine()

    engine.add("Build frontend")
    engine.fail(0, "Frontend build failed")

    alternative = engine.replan(0)

    assert isinstance(alternative, dict)
    assert alternative["original_task"] == "Build frontend"
    assert alternative["reason"] == "Frontend build failed"
    assert "alternative_task" in alternative
    assert alternative["status"] == "pending"


def test_replanning_does_not_trigger_for_successful_task():
    engine = TaskEngine()

    engine.add("Build frontend")
    engine.complete(0)

    assert engine.replan(0) is None