from voice.recorder import record
from voice.listener import listen

audio = record()

text = listen(audio)

print("\nRecognized Text:", text)