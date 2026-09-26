from brains_v2.brain.planner import planner


def test_dynamic_planning_website():
    result = planner.create_plan(
        "Create a professional portfolio website"
    )

    assert result["dynamic"] is True
    assert result["step_count"] >= 5
    assert result["steps"] != [
        "Understand command",
        "Find required module",
        "Execute task",
        "Verify result",
    ]
    assert "Deploy" in result["steps"]


def test_dynamic_planning_python_application():
    result = planner.create_plan(
        "Create a Python application"
    )

    assert result["dynamic"] is True
    assert result["step_count"] >= 5
    assert "Implement Python code" in result["steps"]
    assert "Verify application" in result["steps"]


def test_different_goals_create_different_plans():
    website_plan = planner.create_plan(
        "Create a professional portfolio website"
    )

    chatbot_plan = planner.create_plan(
        "Build an AI chatbot"
    )

    assert website_plan["steps"] != chatbot_plan["steps"]
    assert website_plan["goal"] != chatbot_plan["goal"]