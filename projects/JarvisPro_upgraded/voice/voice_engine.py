from voice.recorder import record
from voice.listener import listen
from voice.speaker import speak


def listen_and_speak():

    audio = record()

    text = listen(audio)

    if not text:
        speak("Sorry, I didn't understand.")
        return ""

    return text