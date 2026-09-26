import tempfile
import logging

log = logging.getLogger("jarvis.voice_v2.listener")

SAMPLE_RATE = 16000


class Listener:
    """Faster-Whisper voice listener with graceful offline fallback."""

    def __init__(self):
        self._model = None
        self._available = None
        self._check()

    def _check(self):
        """Lazy availability check — try once, remember result."""
        if self._available is not None:
            return self._available
        try:
            from faster_whisper import WhisperModel
            self._model = WhisperModel(
                "small",
                device="cpu",
                compute_type="int8",
            )
            self._available = True
        except Exception as e:
            log.info("faster_whisper unavailable (%s); voice input disabled", e)
            self._available = False
        return self._available

    @property
    def available(self) -> bool:
        return self._check()

    def listen(self, seconds=5):
        """Capture audio and return transcribed text, or '' on any failure."""
        if not self.available:
            return ""

        try:
            import sounddevice as sd
            import soundfile as sf
        except Exception as e:
            log.info("sounddevice unavailable (%s)", e)
            return ""

        try:
            audio = sd.rec(
                int(seconds * SAMPLE_RATE),
                samplerate=SAMPLE_RATE,
                channels=1,
                dtype="float32",
            )
            sd.wait()

            with tempfile.NamedTemporaryFile(
                suffix=".wav",
                delete=False,
            ) as file:
                sf.write(file.name, audio, SAMPLE_RATE)
                segments, _ = self._model.transcribe(
                    file.name,
                    language="en",
                    beam_size=1,
                )
                text = "".join(seg.text for seg in segments)
                return text.strip()
        except Exception as e:
            log.info("listen failed (%s)", e)
            return ""


listener = Listener() if Listener()._check() else None
