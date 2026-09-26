from core.synonyms import SYNONYMS


def normalize(command):

    command = command.lower().strip()

    for standard_name, words in SYNONYMS.items():

        for word in words:

            if word in command:

                command = command.replace(word, standard_name)

    return command