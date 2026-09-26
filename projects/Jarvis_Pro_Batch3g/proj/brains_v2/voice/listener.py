"""
Voice Listener
"""

from .microphone import microphone
from .wakeword import wakeword
from conversation.state import is_active

class Listener:

    def wait(self):

        while True:

            text = microphone.listen()

            if not text:
               continue

            print("You:", text)

            if is_active():
                return text

            if wakeword.detect(text):
                return text

listener = Listener()