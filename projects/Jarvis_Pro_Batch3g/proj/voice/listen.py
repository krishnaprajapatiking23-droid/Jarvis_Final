"""
==========================================
JARVIS PRO
Listen Engine
==========================================
"""

from voice.microphone import record
from voice.transcriber import transcribe


def listen():

    audio = record()

    text = transcribe(audio)

    return text