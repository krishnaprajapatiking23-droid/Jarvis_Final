from core.synonyms import SYNONYMS


def find_application(command):

    command = command.lower()

    for app, words in SYNONYMS.items():

        for word in words:

            if word in command:

                return app

    return None