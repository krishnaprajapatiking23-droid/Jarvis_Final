"""
==========================================
JARVIS PRO
Professional Recorder
==========================================
"""

import sounddevice as sd
import soundfile as sf


def record():

    SAMPLE_RATE = 16000
    DURATION = 8

    print("\n🎤 Speak now...\n")

    # Force Python to use the WO Mic device (Device ID = 1)
    recording = sd.rec(
        int(DURATION * SAMPLE_RATE),
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype="float32",
        device=1
    )

    sd.wait()

    sf.write("voice.wav", recording, SAMPLE_RATE)

    return "voice.wav"