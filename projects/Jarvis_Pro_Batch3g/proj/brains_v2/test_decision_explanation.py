from brains_v2.ai.decision import ContextAwareDecision


def test_decision_explanation_for_known_intent():
    decision = ContextAwareDecision()

    data = {
        "command": "open calculator",
        "intent": {"intent": "open_app"},
        "confidence": 95,
        "risk": "Low",
    }

    result = decision.decide(data)

    explanation = result["decision_explanation"]

    assert explanation["decision"] == "execute"
    assert explanation["target"] == "open_app"
    assert explanation["intent"] == "open_app"
    assert explanation["confidence"] == 95
    assert explanation["risk"] == "Low"
    assert explanation["reason"]


def test_decision_explanation_for_low_confidence():
    decision = ContextAwareDecision()

    data = {
        "command": "do something",
        "intent": {"intent": "unknown"},
        "confidence": 40,
        "risk": "None",
    }

    result = decision.decide(data)

    explanation = result["decision_explanation"]

    assert explanation["decision"] == "ask_clarification"
    assert explanation["confidence"] == 40
    assert "low" in explanation["reason"].lower()


def test_decision_explanation_for_high_risk():
    decision = ContextAwareDecision()

    data = {
        "command": "delete all files",
        "intent": {"intent": "unknown"},
        "confidence": 95,
        "risk": "High",
    }

    result = decision.decide(data)

    explanation = result["decision_explanation"]

    assert explanation["decision"] == "request_verification"
    assert explanation["risk"] == "High"
    assert "risk" in explanation["reason"].lower()


def test_decision_explanation_contains_required_fields():
    decision = ContextAwareDecision()

    data = {
        "command": "open calculator",
        "intent": {"intent": "open_app"},
        "confidence": 90,
        "risk": "Low",
    }

    result = decision.decide(data)

    explanation = result["decision_explanation"]

    required_fields = {
        "decision",
        "target",
        "intent",
        "confidence",
        "risk",
        "reason",
    }

    assert required_fields.issubset(
        explanation.keys()
    )