# psychology/emotion.py

import re

EMOTION_KEYWORDS = {
    "happy": [
        "happy", "excited", "great", "awesome",
        "good", "love", "win", "success",
        "amazing", "finally"
    ],

    "sad": [
        "sad", "cry", "depressed", "hurt",
        "lonely", "upset", "lost",
        "failure", "failed"
    ],

    "angry": [
        "angry", "mad", "hate",
        "annoyed", "furious", "irritated"
    ],

    "fear": [
        "afraid", "fear", "nervous",
        "anxious", "scared", "worried"
    ],

    "confident": [
        "confident", "ready", "strong",
        "can do", "believe", "improve"
    ]
}


def clean_text(text):
    return re.sub(r"[^a-zA-Z ]", "", text.lower())


def detect_emotion(text):

    text = clean_text(text)

    scores = {}

    for emotion, words in EMOTION_KEYWORDS.items():

        score = 0

        for word in words:

            if word in text:
                score += 1

        scores[emotion] = score

    ranked = sorted(
        scores.items(),
        key=lambda x: x[1],
        reverse=True
    )

    primary = "neutral"
    secondary = None

    if ranked[0][1] > 0:
        primary = ranked[0][0]

    if len(ranked) > 1 and ranked[1][1] > 0:
        secondary = ranked[1][0]

    stress = 20

    if primary in ["sad", "fear"]:
        stress = 70

    elif primary == "angry":
        stress = 80

    elif primary == "happy":
        stress = 10

    elif primary == "confident":
        stress = 15

    return {
        "primary_emotion": primary,
        "secondary_emotion": secondary,
        "scores": scores,
        "stress_level": stress
    }