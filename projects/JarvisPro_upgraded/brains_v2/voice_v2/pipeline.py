"""Voice pipeline v2 — fast-whisper STT + edge-tts TTS wired to BrainV2."""

import logging

log = logging.getLogger("jarvis.voice_v2.pipeline")


class VoicePipeline:
    """One-shot voice conversation loop."""

    def run(self):
        from brains_v2.voice_v2.listener import listener
        from brains_v2.voice_v2.speaker import speaker
        from brains_v2.manager import brain
        from brains_v2.reply_text import reply_text

        while True:
            print()
            print("=" * 60)
            print("Listening...")

            command = listener.listen() if listener else ""
            if listener is None:
                print("Voice input unavailable (faster_whisper not installed).")
                return

            if not command:
                continue

            print()
            print("You:", command)

            text_lower = command.lower()
            exit_phrases = {
                "jarvis shutdown", "shutdown", "exit", "quit",
                "bye jarvis", "goodbye",
            }
            if any(phrase in text_lower for phrase in exit_phrases):
                speaker.speak("Goodbye. Jarvis is shutting down.")
                break

            try:
                result = brain.process(command)
            except Exception as e:
                log.exception("brain.process failed")
                speaker.speak("Sorry, something went wrong.")
                continue

            reply = reply_text(result)
            print()
            print("Jarvis:", reply)
            speaker.speak(reply)
