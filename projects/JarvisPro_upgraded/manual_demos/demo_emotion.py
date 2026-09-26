from emotion.detector import detect_emotion

while True:

    text = input("You : ")

    if text.lower() == "exit":
        break

    print("Emotion :", detect_emotion(text))
