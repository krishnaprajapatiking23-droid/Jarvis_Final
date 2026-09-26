EMOTIONS = {

    "happy": [
        "happy",
        "great",
        "awesome",
        "excellent",
        "amazing",
        "good",
        "love"
    ],

    "sad": [
        "sad",
        "depressed",
        "upset",
        "cry",
        "hurt"
    ],

    "angry": [
        "angry",
        "annoyed",
        "hate",
        "stupid",
        "idiot"
    ],

    "frustrated": [
        "not working",
        "problem",
        "error",
        "bug",
        "failed",
        "broken"
    ],

    "confused": [
        "confused",
        "don't understand",
        "how",
        "why",
        "explain"
    ],

    "tired": [
        "tired",
        "sleepy",
        "exhausted"
    ]

}


def detect_emotion(text):

    text = text.lower()

    for emotion, words in EMOTIONS.items():

        for word in words:

            if word in text:
                return emotion

    return "neutral"