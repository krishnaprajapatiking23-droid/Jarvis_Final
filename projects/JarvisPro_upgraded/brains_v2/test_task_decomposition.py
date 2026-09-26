from brains_v2.decomposer import decomposer


def test_task_decomposition_website_has_ordered_stages():
    steps = decomposer.decompose(
        "Create a professional portfolio website"
    )

    assert isinstance(steps, list)
    assert len(steps) >= 4

    assert steps.index("Design UI") < steps.index("Build Frontend")
    assert steps.index("Build Frontend") < steps.index("Build Backend")
    assert steps.index("Build Backend") < steps.index("Deploy")


def test_task_decomposition_jarvis_has_core_stages():
    steps = decomposer.decompose(
        "Build a Jarvis AI assistant"
    )

    assert isinstance(steps, list)
    assert len(steps) >= 5

    assert steps.index("Create Brain") < steps.index("Create Memory")
    assert steps.index("Create Memory") < steps.index("Create Voice")
    assert "Test system" in steps
    assert "Verify output" in steps


def test_task_decomposition_different_goals_produce_different_plans():
    website_steps = decomposer.decompose(
        "Create a professional portfolio website"
    )

    python_steps = decomposer.decompose(
        "Create a Python application"
    )

    assert website_steps != python_steps
    assert len(website_steps) >= 5
    assert len(python_steps) >= 5
    assert "Implement Python code" in python_steps
    assert "Deploy" in website_steps