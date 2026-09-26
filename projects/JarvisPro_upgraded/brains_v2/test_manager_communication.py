from brains_v2.tools.manager import ManagerOrchestrator, ManagerMessage


class FakeManagerA:

    def can_handle(self, command):
        return "prepare" in command.lower()

    def execute(self, command):
        return f"A executed: {command}"


class FakeManagerB:

    def can_handle(self, command):
        return "execute" in command.lower()

    def execute(self, command):
        return f"B executed: {command}"


def test_manager_message_contains_sender_receiver_and_command():
    message = ManagerMessage(
        sender="FakeManagerA",
        receiver="FakeManagerB",
        command="execute task",
        data={"value": 123},
    )

    result = message.to_dict()

    assert result["sender"] == "FakeManagerA"
    assert result["receiver"] == "FakeManagerB"
    assert result["command"] == "execute task"
    assert result["data"]["value"] == 123


def test_manager_can_send_message_to_another_manager():
    orchestrator = ManagerOrchestrator()

    manager_a = FakeManagerA()
    manager_b = FakeManagerB()

    orchestrator.managers = [manager_a, manager_b]

    result = orchestrator.send_message(
        sender="FakeManagerA",
        receiver="FakeManagerB",
        command="execute task",
    )

    assert result["status"] == "delivered"
    assert result["result"] == "B executed: execute task"


def test_manager_communication_history_is_recorded():
    orchestrator = ManagerOrchestrator()

    manager_a = FakeManagerA()
    manager_b = FakeManagerB()

    orchestrator.managers = [manager_a, manager_b]

    orchestrator.send_message(
        sender="FakeManagerA",
        receiver="FakeManagerB",
        command="execute task",
    )

    history = orchestrator.communication_history()

    assert len(history) == 1
    assert history[0]["sender"] == "FakeManagerA"
    assert history[0]["receiver"] == "FakeManagerB"


def test_missing_receiver_is_handled():
    orchestrator = ManagerOrchestrator()

    orchestrator.managers = [FakeManagerA()]

    result = orchestrator.send_message(
        sender="FakeManagerA",
        receiver="FakeManagerB",
        command="execute task",
    )

    assert result["status"] == "receiver_not_found"