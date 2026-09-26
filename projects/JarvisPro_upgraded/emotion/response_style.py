STYLES = {

    "happy": {
        "prefix": "😊 Great!",
        "suffix": "I'm happy to help!"
    },

    "sad": {
        "prefix": "💙 I understand.",
        "suffix": "We'll solve this together."
    },

    "frustrated": {
        "prefix": "💪 Don't worry.",
        "suffix": "Let's fix this step by step."
    },

    "confused": {
        "prefix": "📚 No problem.",
        "suffix": "I'll explain it in a simpler way."
    },

    "tired": {
        "prefix": "😌 Take your time.",
        "suffix": "I'll keep things simple."
    },

    "angry": {
        "prefix": "🙂 I understand your frustration.",
        "suffix": "Let's focus on solving the problem."
    },

    "neutral": {
        "prefix": "",
        "suffix": ""
    }

}


def style_answer(answer, emotion):

    style = STYLES.get(emotion, STYLES["neutral"])

    return f"{style['prefix']}\n\n{answer}\n\n{style['suffix']}"