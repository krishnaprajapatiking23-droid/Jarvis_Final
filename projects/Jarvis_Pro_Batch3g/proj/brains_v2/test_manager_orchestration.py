from brains_v2.tools.manager import ManagerOrchestrator


class FakeManagerA:

    def can_handle(self, command):
        return True

    def execute(self, command):
        return "Manager A executed"


class FakeManagerB:

    def can_handle(self, command):
        return True

    def execute(self, command):
        return "Manager B executed"


class FakeManagerC:

    def can_handle(self, command):
        return False

    def execute(self, command):
        return "Manager C executed"


def test_orchestrator_finds_multiple_managers():
    orchestrator = ManagerOrchestrator()

    orchestrator.managers = [
        FakeManagerA(),
        FakeManagerB(),
        FakeManagerC()
    ]

    managers = orchestrator.find_managers("test command")

    assert len(managers) == 2


def test_orchestrator_executes_multiple_managers():
    orchestrator = ManagerOrchestrator()

    orchestrator.managers = [
        FakeManagerA(),
        FakeManagerB()
    ]

    result = orchestrator.orchestrate("test command")

    assert result["status"] == "completed"
    assert result["manager_count"] == 2
    assert len(result["results"]) == 2
    assert result["results"][0]["result"] == "Manager A executed"
    assert result["results"][1]["result"] == "Manager B executed"


def test_orchestrator_handles_no_manager():
    orchestrator = ManagerOrchestrator()

    orchestrator.managers = [
        FakeManagerC()
    ]

    result = orchestrator.orchestrate("test command")

    assert result["status"] == "no_manager"
    assert result["manager_count"] == 0
    assert result["results"] == []