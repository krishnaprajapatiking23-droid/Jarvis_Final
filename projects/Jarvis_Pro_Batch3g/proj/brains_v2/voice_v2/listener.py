import tempfile
import sounddevice as sd
import soundfile as sf

from faster_whisper import WhisperModel


class Listener:

    def __init__(self):

        self.model = WhisperModel(

            "small",

            device="cpu",

            compute_type="int8"
        )

    def listen(self, seconds=5):

        sample_rate = 16000

        audio = sd.rec(

            int(seconds * sample_rate),

            samplerate=sample_rate,

            channels=1,

            dtype="float32"
        )

        sd.wait()

        with tempfile.NamedTemporaryFile(

            suffix=".wav",

            delete=False

        ) as file:

            sf.write(

                file.name,

                audio,

                sample_rate
            )

            segments, _ = self.model.transcribe(
                file.name,
                language="en",
                beam_size=1
            )

        text = ""

        for segment in segments:

            text += segment.text

        return text.strip()


listener = Listener()