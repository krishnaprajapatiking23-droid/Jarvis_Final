from conversation.identity import identity

from voice.voice_engine import listen_and_speak
from voice.speaker import speak


WAKE_WORD = "jarvis"


def wait_for_wake_word():

    while True:

        print("\n🎤 Waiting for wake word...")

        text = listen_and_speak()

        if not text:
            continue

        if WAKE_WORD in text.lower():

            owner = identity.owner()

            speak(f"Yes {owner}?" if owner else "Yes?")

            return