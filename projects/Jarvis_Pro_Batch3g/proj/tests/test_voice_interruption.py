"""
Tests for real conversation interruption (feature 3.15) and for the
legacy modules repaired alongside it.

These tests never touch the audio hardware: the text-to-speech core
falls back to printing when pyttsx3 is unavailable, which is exactly
the path exercised here.
"""

from brains_v2.voice.speaker import Speaker, speaker
from conversation.interruption import interruption_handler
from voice.barge_in import BargeInMonitor, barge_in
from voice.tts import InterruptibleTTS


class FakeSpeaker:
    """Minimal speaker used to drive the barge-in monitor."""

    def __init__(self, speaking=False):
        self.speaking = speaking
        self.stopped = False

    def is_speaking(self):
        return self.speaking

    def stop(self):
        self.stopped = True
        self.speaking = False
        return True


# ----------------------------------------------------------------------
# text to speech core
# ----------------------------------------------------------------------
def test_tts_speak_returns_the_spoken_line():
    engine = InterruptibleTTS(echo=False)

    spoken = engine.speak("Chrome is open.")

    assert spoken == "Chrome is open."
    assert engine.last_spoken == "Chrome is open."
    assert engine.wait(2) is True
    assert engine.is_speaking() is False


def test_tts_ignores_empty_text():
    engine = InterruptibleTTS(echo=False)

    assert engine.speak("") == ""
    assert engine.speak("   ") == ""


def test_tts_async_speech_does_not_block():
    engine = InterruptibleTTS(echo=False)

    engine.speak("A long explanation about Python.", wait=False)

    assert engine.last_spoken == "A long explanation about Python."
    assert engine.wait(2) is True


def test_tts_stop_interrupts_and_clears_the_queue():
    engine = InterruptibleTTS(echo=False)

    for line in ("first sentence", "second sentence", "third sentence"):
        engine.speak(line, wait=False)

    engine.stop()

    assert engine.interrupted is True
    assert engine.is_speaking() is False
    assert engine.wait(2) is True


def test_tts_stop_is_safe_when_silent():
    engine = InterruptibleTTS(echo=False)

    assert engine.stop() is True


def test_speaking_again_clears_the_interrupted_flag():
    engine = InterruptibleTTS(echo=False)

    engine.speak("one", wait=False)
    engine.stop()
    engine.speak("two")

    assert engine.interrupted is False


# ----------------------------------------------------------------------
# speaker wrappers keep their old API
# ----------------------------------------------------------------------
def test_speaker_supports_interruption_api():
    voice = Speaker()

    assert callable(voice.stop)
    assert callable(voice.speak)
    assert callable(voice.is_speaking)
    assert voice.stop() is True


def test_speakers_share_one_engine():
    assert Speaker().engine is speaker.engine


def test_root_speaker_module_can_stop():
    from voice import speaker as root_speaker

    assert callable(root_speaker.speak)
    assert root_speaker.stop() is True
    assert root_speaker.is_speaking() is False


def test_interruption_handler_silences_the_voice_layer():
    assert interruption_handler.silence_voice() is True


def test_interruption_handler_still_reports_the_acknowledgement():
    report = interruption_handler.detect("wait")
    reply = interruption_handler.handle(report["kind"])

    assert report["interrupt"] is True
    assert report["kind"] == "pause"
    assert reply


# ----------------------------------------------------------------------
# barge-in monitor
# ----------------------------------------------------------------------
def test_barge_in_recognises_interruption_phrases():
    monitor = BargeInMonitor()

    assert monitor.matches("stop") == "stop"
    assert monitor.matches("wait") == "pause"
    assert monitor.matches("never mind") == "cancel"


def test_barge_in_ignores_normal_speech():
    monitor = BargeInMonitor()

    assert monitor.matches("open chrome") == ""
    assert monitor.matches("stop the music") == ""
    assert monitor.matches("") == ""


def test_barge_in_watch_never_breaks_the_pipeline():
    monitor = BargeInMonitor()
    fake = FakeSpeaker()

    with monitor.watch(fake):
        pass

    assert fake.stopped is False


def test_barge_in_reports_its_configuration_state():
    assert isinstance(barge_in.enabled(), bool)


# ----------------------------------------------------------------------
# legacy modules repaired with this change
# ----------------------------------------------------------------------
def test_owner_lookup_survives_a_missing_owner_file():
    from security import owner_manager

    assert isinstance(owner_manager.load_owner(), dict)
    assert isinstance(owner_manager.owner_name(), str)
    assert owner_manager.is_owner("") is False


def test_legacy_context_helpers_do_not_raise():
    from conversation import manager as legacy

    context = legacy.remember("open_app", "chrome", "open chrome")

    assert context.last_intent == "open_app"
    assert context.last_app == "chrome"
    assert legacy.current() is context


def test_legacy_history_is_capped():
    from conversation import history as history_module
    from conversation import manager as legacy

    history_module.history.clear()
    for index in range(history_module.MAX_HISTORY + 5):
        legacy.add_history(f"question {index}", f"answer {index}")

    assert len(legacy.get_history()) == history_module.MAX_HISTORY
