from brains_v2.voice.speaker import Speaker


def test_speaker_supports_interruption():
    speaker = Speaker()

    assert hasattr(speaker, "stop")
    assert callable(speaker.stop)


def test_speaker_stop_can_be_called_safely():
    speaker = Speaker()

    speaker.stop()

    assert True