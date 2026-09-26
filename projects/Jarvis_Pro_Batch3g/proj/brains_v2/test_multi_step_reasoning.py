from brains_v2.reasoning_engine import reasoning_engine


def test_multi_step_reasoning_detects_ordered_actions():
    result = reasoning_engine.analyze(
        "send an email to my teacher and then open the attachment"
    )

    assert result["goal"] == "Execute multiple actions"
    assert result["ordered_actions"] == ["email", "open"]


def test_multi_step_reasoning_creates_execution_steps():
    result = reasoning_engine.analyze(
        "search for Python tutorials and then open the first result"
    )

    assert "steps" in result
    assert isinstance(result["steps"], list)
    assert len(result["steps"]) >= 2


def test_multi_step_reasoning_preserves_step_order():
    result = reasoning_engine.analyze(
        "search for Python tutorials and then open the first result"
    )

    steps = result["steps"]

    assert steps[0]["action"] == "search"
    assert steps[1]["action"] == "open"
    assert steps[0]["order"] == 1
    assert steps[1]["order"] == 2