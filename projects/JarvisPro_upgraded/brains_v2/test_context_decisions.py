from brains_v2.ai.decision import ContextAwareDecision


def test_context_is_saved_from_previous_command():
    decision = ContextAwareDecision()

    first = {
        "command": "open calculator",
        "intent": {"intent": "open_app"}
    }

    decision.decide(first)

    context = decision.get_context()

    assert context["last_command"] == "open calculator"
    assert context["last_intent"]["intent"] == "open_app"


def test_context_is_added_to_next_decision():
    decision = ContextAwareDecision()

    decision.decide({
        "command": "open calculator",
        "intent": {"intent": "open_app"}
    })

    second = {
        "command": "close it",
        "intent": {"intent": "conversation"}
    }

    result = decision.decide(second)

    assert "context" in result
    assert result["context"]["last_command"] == "close it"
    assert result["context"]["last_intent"]["intent"] == "conversation"


def test_context_updates_when_new_command_arrives():
    decision = ContextAwareDecision()

    decision.decide({
        "command": "open calculator",
        "intent": {"intent": "open_app"}
    })

    decision.decide({
        "command": "open notepad",
        "intent": {"intent": "open_app"}
    })

    context = decision.get_context()

    assert context["last_command"] == "open notepad"
    assert context["last_intent"]["intent"] == "open_app"