from brains_v2.psychology.database import get_owner, save_owner

DEFAULT_PERSONALITY = {
    "introversion": 50,
    "confidence": 50,
    "curiosity": 50,
    "discipline": 50,
    "leadership": 50,
    "patience": 50,
    "optimism": 50,
    "growth_mindset": 50
}


def get_personality():

    owner = get_owner()

    if "personality" not in owner:
        owner["personality"] = DEFAULT_PERSONALITY.copy()
        save_owner(owner)

    return owner["personality"]


def save_personality(profile):

    owner = get_owner()

    owner["personality"] = profile

    save_owner(owner)


def update_trait(trait, change):

    profile = get_personality()

    if trait not in profile:
        return False

    profile[trait] += change

    profile[trait] = max(0, min(100, profile[trait]))

    save_personality(profile)

    return True


def reset_personality():

    save_personality(DEFAULT_PERSONALITY.copy())