from brains_v2.psychology.analyzer import analyze


def test_analyzer():

    texts = [
        "I am very happy today.",
        "I failed my exam.",
        "I am nervous before my interview.",
        "I hate this project.",
        "I am ready to win."
    ]

    for text in texts:

        result = analyze(text)

        assert result is not None
        assert isinstance(result, (dict, str))