from brains_v2.dependency_graph import DependencyGraph


def test_dependency_can_be_added():
    graph = DependencyGraph()

    graph.add_dependency(
        "Build Frontend",
        "Design UI",
    )

    assert graph.get_dependencies(
        "Build Frontend"
    ) == ["Design UI"]


def test_execution_order_respects_dependencies():
    graph = DependencyGraph()

    graph.add_dependency(
        "Build Frontend",
        "Design UI",
    )

    graph.add_dependency(
        "Build Backend",
        "Build Frontend",
    )

    graph.add_dependency(
        "Testing",
        "Build Backend",
    )

    order = graph.execution_order()

    assert order.index("Design UI") < order.index(
        "Build Frontend"
    )

    assert order.index("Build Frontend") < order.index(
        "Build Backend"
    )

    assert order.index("Build Backend") < order.index(
        "Testing"
    )


def test_ready_tasks_only_include_satisfied_dependencies():
    graph = DependencyGraph()

    graph.add_dependency(
        "Build Frontend",
        "Design UI",
    )

    graph.add_dependency(
        "Testing",
        "Build Frontend",
    )

    ready = graph.get_ready_tasks(
        completed={"Design UI"}
    )

    assert ready == ["Build Frontend"]


def test_cycle_is_rejected():
    graph = DependencyGraph()

    graph.add_dependency(
        "Task A",
        "Task B",
    )

    graph.add_dependency(
        "Task B",
        "Task C",
    )

    try:
        graph.add_dependency(
            "Task C",
            "Task A",
        )
        assert False, "Expected cycle to be rejected"
    except ValueError as error:
        assert "cycle" in str(error).lower()


def test_graph_can_be_serialized():
    graph = DependencyGraph()

    graph.add_dependency(
        "Build",
        "Design",
    )

    result = graph.to_dict()

    assert result == {
        "Build": ["Design"],
        "Design": [],
    }