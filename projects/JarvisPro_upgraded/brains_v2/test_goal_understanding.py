from brains_v2.reasoning_engine import reasoning_engine


def test_goal_understanding_create_website():
    result = reasoning_engine.analyze(
        "I want to create a portfolio website"
    )

    assert result["goal"] == "Create a portfolio website"


def test_goal_understanding_fix_project():
    result = reasoning_engine.analyze(
        "I need to fix my Python project"
    )

    assert result["goal"] == "Fix a Python project"


def test_goal_understanding_learning():
    result = reasoning_engine.analyze(
        "I want to learn Python"
    )

    assert result["goal"] == "Learn Python"