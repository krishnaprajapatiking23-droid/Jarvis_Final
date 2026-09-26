from brains_v2.followup import FollowUpEngine


def test_followup_understands_previous_topic():
    engine = FollowUpEngine()

    result = engine.understand(
        "I want to build a Python website"
    )

    assert result["understood"] is True
    assert result["topic"] == "Python website"


def test_followup_understands_followup_command():
    engine = FollowUpEngine()

    engine.understand("I want to build a Python website")

    result = engine.understand("make it responsive")

    assert result["understood"] is True
    assert result["reference"] == "Python website"
    assert "responsive" in result["follow_up"].lower()


def test_followup_detects_no_previous_context():
    engine = FollowUpEngine()

    result = engine.understand("make it better")

    assert result["understood"] is False