from brains_v2.agent.task import ExecutionContext, Task


def test_execution_context_stores_environment():
    context = ExecutionContext(
        working_directory="C:\\Projects\\Jarvis",
        active_manager="CodingManager",
        current_step=2,
    )

    assert context.working_directory == "C:\\Projects\\Jarvis"
    assert context.active_manager == "CodingManager"
    assert context.current_step == 2


def test_execution_context_stores_variables():
    context = ExecutionContext()

    context.set_variable("language", "Python")
    context.set_variable("version", "3.12")

    assert context.get_variable("language") == "Python"
    assert context.get_variable("version") == "3.12"
    assert context.get_variable("missing", "default") == "default"


def test_execution_context_stores_metadata():
    context = ExecutionContext()

    context.set_metadata("session", "test-session")
    context.set_metadata("attempt", 1)

    assert context.metadata["session"] == "test-session"
    assert context.metadata["attempt"] == 1


def test_task_contains_execution_context():
    task = Task(goal="Build application")

    task.execution_context.working_directory = (
        "C:\\Projects\\Jarvis"
    )
    task.execution_context.active_manager = "CodingManager"
    task.execution_context.current_step = 1

    assert task.execution_context.working_directory == (
        "C:\\Projects\\Jarvis"
    )
    assert task.execution_context.active_manager == "CodingManager"
    assert task.execution_context.current_step == 1


def test_execution_context_is_serialized_with_task():
    task = Task(goal="Run tests")

    task.execution_context.set_variable(
        "test_command",
        "pytest"
    )

    task.execution_context.set_metadata(
        "attempt",
        1
    )

    data = task.to_dict()

    assert "execution_context" in data
    assert data["execution_context"]["variables"]["test_command"] == "pytest"
    assert data["execution_context"]["metadata"]["attempt"] == 1