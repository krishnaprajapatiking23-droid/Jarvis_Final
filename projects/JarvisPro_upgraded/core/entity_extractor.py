from core.synonyms import SYNONYMS


def extract(command):

    text = command.lower()

    for entity, words in SYNONYMS.items():

        for word in words:

            if word in text:
                return entity

    return None