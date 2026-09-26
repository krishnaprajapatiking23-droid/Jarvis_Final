EMOTIONS = {

    "neutral": {
        "emoji": "🙂",
        "style": "normal"
    },

    "happy": {
        "emoji": "😊",
        "style": "friendly"
    },

    "focused": {
        "emoji": "🎯",
        "style": "professional"
    },

    "excited": {
        "emoji": "🚀",
        "style": "energetic"
    },

    "thinking": {
        "emoji": "🤔",
        "style": "analytical"
    }

}


current_emotion = "neutral"


def set_emotion(name):

    global current_emotion

    if name in EMOTIONS:

        current_emotion = name


def get_emotion():

    return current_emotion


def emoji():

    return EMOTIONS[current_emotion]["emoji"]