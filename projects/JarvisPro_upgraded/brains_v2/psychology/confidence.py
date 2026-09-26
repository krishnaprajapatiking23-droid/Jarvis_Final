# psychology/confidence.py

from brains_v2.psychology.database import get_owner, save_owner


DEFAULT_PROFILE = {
    "confidence": 50,
    "social_confidence": 50,
    "stress": 20,
    "communication": 50,
    "leadership": 50,
    "focus": 70
}


def get_confidence_profile():
    owner = get_owner()

    if not owner:
        save_owner(DEFAULT_PROFILE)
        return DEFAULT_PROFILE

    profile = DEFAULT_PROFILE.copy()
    profile.update(owner)

    return profile


def update_score(name, change):
    profile = get_confidence_profile()

    if name not in profile:
        return profile

    profile[name] += change

    if profile[name] > 100:
        profile[name] = 100

    if profile[name] < 0:
        profile[name] = 0

    save_owner(profile)

    return profile