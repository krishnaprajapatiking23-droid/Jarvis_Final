from brains_v2.ai.decision import ContextAwareDecision


def test_high_risk_action_creates_approval_checkpoint():
    decision = ContextAwareDecision()

    data = {
        "command": "delete all files",
        "intent": {"intent": "unknown"},
        "confidence": 95,
        "risk": "High",
    }

    result = decision.decide(data)

    assert result["autonomous_decision"]["action"] == (
        "request_verification"
    )

    assert "approval_checkpoint" in result

    checkpoint = result["approval_checkpoint"]

    assert checkpoint["status"] == "pending"
    assert checkpoint["risk"] == "High"


def test_pending_approval_can_be_approved():
    decision = ContextAwareDecision()

    data = {
        "command": "delete all files",
        "intent": {"intent": "unknown"},
        "confidence": 95,
        "risk": "High",
    }

    decision.decide(data)

    approved = decision.approve(0)

    assert approved is not None
    assert approved["status"] == "approved"


def test_pending_approval_can_be_rejected():
    decision = ContextAwareDecision()

    data = {
        "command": "delete all files",
        "intent": {"intent": "unknown"},
        "confidence": 95,
        "risk": "High",
    }

    decision.decide(data)

    rejected = decision.reject(0)

    assert rejected is not None
    assert rejected["status"] == "rejected"


def test_pending_approval_count():
    decision = ContextAwareDecision()

    data = {
        "command": "delete all files",
        "intent": {"intent": "unknown"},
        "confidence": 95,
        "risk": "High",
    }

    decision.decide(data)
    decision.decide(data)

    assert decision.pending_approval_count() == 2

    decision.approve(0)

    assert decision.pending_approval_count() == 1


def test_safe_action_does_not_require_approval():
    decision = ContextAwareDecision()

    data = {
        "command": "open calculator",
        "intent": {"intent": "open_app"},
        "confidence": 95,
        "risk": "Low",
    }

    result = decision.decide(data)

    assert result["autonomous_decision"]["action"] == "execute"
    assert "approval_checkpoint" not in result