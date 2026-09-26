"""
==========================================
JARVIS PRO
Advanced Whisper Engine
==========================================
"""

from faster_whisper import WhisperModel

print("Loading Whisper AI...")

model = WhisperModel(
    "small",
    device="cpu",
    compute_type="int8"
)


def transcribe(audio_file):

    segments, info = model.transcribe(
        audio_file,
        language="en",
        beam_size=5,
        vad_filter=True
    )

    text = ""

    for segment in segments:
        text += segment.text + " "

    text = text.strip()

    print("\n================================")
    print("Recognized Speech")
    print("================================")
    print(text)
    print("================================\n")

    return text