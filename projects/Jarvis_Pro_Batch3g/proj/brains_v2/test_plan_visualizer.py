from brains_v2.plan_visualizer import PlanVisualizer


def test_plan_visualizer_builds_nodes_and_edges():
    visualizer = PlanVisualizer()

    result = visualizer.build_tree(
        "Build portfolio website",
        [
            "Design UI",
            "Build Frontend",
            "Build Backend",
            "Testing",
        ],
    )

    assert result["goal"] == "Build portfolio website"
    assert result["step_count"] == 4
    assert len(result["nodes"]) == 5
    assert len(result["edges"]) == 4


def test_plan_visualizer_preserves_step_order():
    visualizer = PlanVisualizer()

    result = visualizer.build_tree(
        "Build application",
        [
            "Design",
            "Code",
            "Test",
        ],
    )

    steps = [
        node
        for node in result["nodes"]
        if node["type"] == "step"
    ]

    assert steps[0]["label"] == "Design"
    assert steps[1]["label"] == "Code"
    assert steps[2]["label"] == "Test"

    assert steps[0]["order"] == 1
    assert steps[1]["order"] == 2
    assert steps[2]["order"] == 3


def test_plan_visualizer_creates_readable_text():
    visualizer = PlanVisualizer()

    result = visualizer.to_text(
        "Build application",
        [
            "Design",
            "Code",
            "Test",
        ],
    )

    assert "Goal: Build application" in result
    assert "1. Design" in result
    assert "2. Code" in result
    assert "3. Test" in result


def test_plan_visualizer_creates_mermaid_graph():
    visualizer = PlanVisualizer()

    result = visualizer.to_mermaid(
        "Build application",
        [
            "Design",
            "Code",
            "Test",
        ],
    )

    assert "flowchart TD" in result
    assert 'G["Build application"]' in result
    assert 'S1["Design"]' in result
    assert 'S2["Code"]' in result
    assert 'S3["Test"]' in result
    assert "G --> S1" in result
    assert "S1 --> S2" in result
    assert "S2 --> S3" in result


def test_plan_visualizer_escapes_quotes():
    visualizer = PlanVisualizer()

    result = visualizer.to_mermaid(
        'Build "Jarvis"',
        ['Create "Brain"'],
    )

    assert "'Jarvis'" in result
    assert "'Brain'" in result