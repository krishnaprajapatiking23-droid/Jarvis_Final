from brains_v2.topic_tracker import TopicTracker


def test_switches_from_one_topic_to_another():
    tracker = TopicTracker()

    tracker.track("I am working on Python")
    result = tracker.track("Let's talk about Minecraft")

    assert result["changed"] is True
    assert result["previous_topic"] == "Python"
    assert result["current_topic"] == "Minecraft"


def test_no_switch_when_topic_stays_same():
    tracker = TopicTracker()

    tracker.track("I am working on Python")
    result = tracker.track("I need help with Python")

    assert result["changed"] is False
    assert result["current_topic"] == "Python"


def test_multiple_topic_switches():
    tracker = TopicTracker()

    tracker.track("I am learning Python")
    tracker.track("Let's talk about Minecraft")
    result = tracker.track("I want to learn guitar")

    assert result["changed"] is True
    assert result["previous_topic"] == "Minecraft"
    assert result["current_topic"] == "guitar"


def test_switch_history_is_preserved():
    tracker = TopicTracker()

    tracker.track("I am learning Python")
    tracker.track("Let's talk about Minecraft")
    tracker.track("I want to learn guitar")

    history = tracker.history()

    assert history == ["Python", "Minecraft", "guitar"]