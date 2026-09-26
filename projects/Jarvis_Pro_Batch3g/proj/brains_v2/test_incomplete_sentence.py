from brains_v2.incomplete_sentence import IncompleteSentenceEngine


def test_detects_trailing_ellipsis():
    engine = IncompleteSentenceEngine()

    result = engine.analyze("open the...")

    assert result["incomplete"] is True
    assert result["reason"] == "trailing_ellipsis"


def test_detects_incomplete_command():
    engine = IncompleteSentenceEngine()

    result = engine.analyze("I want to create a")

    assert result["incomplete"] is True
    assert result["reason"] == "unfinished_phrase"


def test_accepts_complete_sentence():
    engine = IncompleteSentenceEngine()

    result = engine.analyze("Open the calculator")

    assert result["incomplete"] is False
    assert result["completion_needed"] is False


def test_detects_action_without_object():
    engine = IncompleteSentenceEngine()

    result = engine.analyze("open the")

    assert result["incomplete"] is True
    assert result["reason"] == "missing_object"