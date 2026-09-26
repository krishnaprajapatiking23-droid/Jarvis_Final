import speech_recognition as sr


def listen(audio_file):

    recognizer = sr.Recognizer()

    with sr.AudioFile(audio_file) as source:

        audio = recognizer.record(source)

    try:

        text = recognizer.recognize_google(audio)

        print("\nYou said:", text)

        return text

    except sr.UnknownValueError:

        print("Sorry, I couldn't understand.")

        return ""

    except sr.RequestError:

        print("No internet connection.")

        return ""