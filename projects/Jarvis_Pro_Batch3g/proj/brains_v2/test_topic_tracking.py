from brains_v2.topic_tracker import TopicTracker


def test_tracks_first_topic():
    tracker = TopicTracker()

    result = tracker.track("I want to build a Python website")

    assert result["topic"] == "Python website"
    assert result["current_topic"] == "Python website"


def test_keeps_topic_across_related_messages():
    tracker = TopicTracker()

    tracker.track("I want to build a Python website")
    result = tracker.track("Make it responsive")

    assert result["current_topic"] == "Python website"
    assert result["changed"] is False


def test_detects_topic_change():
    tracker = TopicTracker()

    tracker.track("I want to build a Python website")
    result = tracker.track("Now let's talk about Minecraft")

    assert result["current_topic"] == "Minecraft"
    assert result["previous_topic"] == "Python website"
    assert result["changed"] is True


def test_keeps_topic_history():
    tracker = TopicTracker()

    tracker.track("I am working on Python")
    tracker.track("Let's talk about Minecraft")
    tracker.track("Now I want to discuss guitar")

    history = tracker.history()

    assert "Python" in history
    assert "Minecraft" in history
    assert "guitar" in history