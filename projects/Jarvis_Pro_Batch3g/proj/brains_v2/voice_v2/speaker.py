import asyncio
import edge_tts
import tempfile
import os
import winsound


VOICE = "en-US-GuyNeural"


class Speaker:

    async def _speak(self, text):

        with tempfile.NamedTemporaryFile(

            delete=False,

            suffix=".mp3"

        ) as file:

            filename = file.name

        communicate = edge_tts.Communicate(

            text=text,

            voice=VOICE

        )

        await communicate.save(filename)

        winsound.PlaySound(

            filename,

            winsound.SND_FILENAME

        )

        os.remove(filename)

    def speak(self, text):

        asyncio.run(

            self._speak(text)

        )


speaker = Speaker()