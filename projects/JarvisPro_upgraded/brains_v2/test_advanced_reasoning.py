from brains_v2.reasoning_engine import reasoning_engine


def test_advanced_reasoning_open_command():
    result = reasoning_engine.analyze("open calculator")

    assert isinstance(result, dict)
    assert "goal" in result
    assert "risk" in result
    assert "confidence" in result
    assert result["goal"] == "Open an application"
    assert 0 <= result["confidence"] <= 100


def test_advanced_reasoning_build_command():
    result = reasoning_engine.analyze(
        "build a Python application"
    )

    assert isinstance(result, dict)
    assert result["goal"] == "Create a Python application"
    assert result["risk"] == "Medium"
    assert 0 <= result["confidence"] <= 100