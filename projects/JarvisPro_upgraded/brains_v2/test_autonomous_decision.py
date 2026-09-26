from brains_v2.ai.decision import ContextAwareDecision


def test_high_confidence_known_intent_executes():
    decision = ContextAwareDecision()

    result = decision.autonomous_decision({
        "intent": {
            "intent": "open_app"
        },
        "confidence": 95,
        "risk": "Low"
    })

    assert result["decision"] == "execute"
    assert result["action"] == "open_app"


def test_low_confidence_requests_clarification():
    decision = ContextAwareDecision()

    result = decision.autonomous_decision({
        "intent": {
            "intent": "unknown"
        },
        "confidence": 40,
        "risk": "None"
    })

    assert result["decision"] == "ask_clarification"
    assert result["action"] is None


def test_high_risk_requests_verification():
    decision = ContextAwareDecision()

    result = decision.autonomous_decision({
        "intent": {
            "intent": "delete_files"
        },
        "confidence": 95,
        "risk": "High"
    })

    assert result["decision"] == "request_verification"
    assert result["action"] is None


def test_unknown_intent_does_not_execute():
    decision = ContextAwareDecision()

    result = decision.autonomous_decision({
        "intent": {
            "intent": "unknown"
        },
        "confidence": 90,
        "risk": "Low"
    })

    assert result["decision"] == "ask_clarification"
    assert result["action"] is None