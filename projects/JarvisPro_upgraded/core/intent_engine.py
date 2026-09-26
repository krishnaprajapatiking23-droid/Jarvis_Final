from core.command_classifier import classify
from core.entity_extractor import extract


def understand(command):

    intent = classify(command)

    entity = extract(command)

    return {
        "intent": intent,
        "entity": entity,
        "text": command
    }