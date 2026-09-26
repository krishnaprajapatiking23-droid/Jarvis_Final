import logging
import tempfile
import os

log = logging.getLogger("jarvis.voice_v2.speaker")


class Speaker:
    """TTS speaker with graceful offline fallback to print-only."""

    VOICE = "en-US-GuyNeural"

    def speak(self, text):
        """Say text, or print it when audio is unavailable."""
        if not text:
            return
        try:
            self._edge_speak(text)
        except Exception as e:
            log.info("edge-tts failed (%s); printing instead", e)
            print(f"Jarvis: {text}")

    def _edge_speak(self, text):
        """Speak via edge-tts (Windows only, needs network)."""
        import asyncio
        import edge_tts
        import winsound

        async def _speak():
            with tempfile.NamedTemporaryFile(
                delete=False,
                suffix=".mp3",
            ) as tmp:
                fname = tmp.name
            try:
                communicate = edge_tts.Communicate(text=text, voice=self.VOICE)
                await communicate.save(fname)
                winsound.PlaySound(fname, winsound.SND_FILENAME)
            finally:
                try:
                    os.remove(fname)
                except Exception:
                    pass

        asyncio.run(_speak())


speaker = Speaker()
