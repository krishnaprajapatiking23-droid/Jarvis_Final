from brains_v2.voice_v2.listener import listener
from brains_v2.voice_v2.speaker import speaker

from brains_v2.manager import brain


class VoicePipeline:

    def run(self):

        while True:

            print()

            print("=" * 60)

            print("Listening...")

            command = listener.listen()

            if not command:

                continue

            print()

            print("You :", command)

            text = command.lower()

            if any(x in text for x in [

                "jarvis shutdown",

                "shutdown",

                "exit",

                "quit",

                "bye jarvis",

                "goodbye"

            ]):

                speaker.speak("Goodbye. Jarvis is shutting down.")

                break

            try:

                result = brain.process(command)

            except Exception as e:

                print()

                print("ERROR :", e)

                speaker.speak(

                    "Sorry, something went wrong."

                )

                continue

            from brains_v2.reply_text import reply_text

            reply = reply_text(result)

            print()

            print("Jarvis :", reply)

            speaker.speak(reply)


pipeline = VoicePipeline()