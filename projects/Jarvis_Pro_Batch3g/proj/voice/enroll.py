import shutil


def enroll_owner(recorded_voice):

    destination = "models/owner/owner_voice.wav"

    shutil.copy(recorded_voice, destination)

    print()

    print("Owner voice enrolled successfully.")