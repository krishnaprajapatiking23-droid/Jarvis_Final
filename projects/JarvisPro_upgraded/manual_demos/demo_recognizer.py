from voice.recorder import record
from voice.recognizer import recognize

audio = record()

text = recognize(audio)

print(text)