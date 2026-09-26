import pyttsx3

engine = pyttsx3.init()

engine.setProperty("rate", 175)

engine.say("Hello Krishna. Can you hear me?")
engine.runAndWait()

print("Voice test completed.")