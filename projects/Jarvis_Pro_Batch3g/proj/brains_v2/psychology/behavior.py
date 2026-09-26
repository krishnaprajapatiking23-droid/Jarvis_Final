from brains_v2.psychology.personality import update_trait

BEHAVIOR_RULES = {

    "completed_task": {
        "discipline": 3,
        "confidence": 1
    },

    "studied": {
        "discipline": 2,
        "curiosity": 2
    },

    "built_project": {
        "curiosity": 3,
        "confidence": 2
    },

    "helped_someone": {
        "patience": 2,
        "leadership": 1
    },

    "exercise": {
        "discipline": 1,
        "confidence": 1
    },

    "gave_up": {
        "confidence": -2,
        "discipline": -1
    },

    "learned_new_skill": {
        "curiosity": 3,
        "growth_mindset": 2
    }
}


def record_behavior(action):

    if action not in BEHAVIOR_RULES:
        return False

    changes = BEHAVIOR_RULES[action]

    for trait, value in changes.items():
        update_trait(trait, value)

    return True