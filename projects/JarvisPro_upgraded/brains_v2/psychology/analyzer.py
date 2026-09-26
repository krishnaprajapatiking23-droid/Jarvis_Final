from brains_v2.psychology.personality import get_personality
from brains_v2.psychology.emotion import detect_emotion

def analyze(text):

    personality = get_personality()

    emotion = detect_emotion(text)

    report = {

        "emotion": emotion,

        "personality": personality,

        "summary": generate_summary(
            personality,
            emotion
        )

    }

    return report


def generate_summary(personality, emotion):

    summary = []

    if personality["confidence"] >= 70:
        summary.append(
            "High confidence."
        )

    elif personality["confidence"] >= 50:
        summary.append(
            "Average confidence."
        )

    else:
        summary.append(
            "Confidence needs improvement."
        )

    if personality["discipline"] >= 70:
        summary.append(
            "Highly disciplined."
        )

    elif personality["discipline"] >= 50:
        summary.append(
            "Moderately disciplined."
        )

    else:
        summary.append(
            "Needs better discipline."
        )

    if personality["curiosity"] >= 70:
        summary.append(
            "Very curious learner."
        )

    elif personality["curiosity"] >= 50:
        summary.append(
            "Learns consistently."
        )

    else:
        summary.append(
            "Should explore more."
        )

    summary.append(
        f"Current emotion: {emotion['primary_emotion']}"
    )

    return summary