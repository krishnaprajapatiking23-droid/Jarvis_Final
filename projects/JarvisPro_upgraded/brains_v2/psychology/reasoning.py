"""
=========================================================
Jarvis Human Intelligence System
Reasoning Engine V1
=========================================================
"""

from brains_v2.psychology.emotion import detect_emotion
from brains_v2.psychology.personality import get_personality


class PsychologyReasoner:

    def __init__(self):

        self.personality = get_personality()

    def analyze(self, text):

        emotion = detect_emotion(text)

        report = {
            "emotion": emotion,
            "personality": self.personality,
            "advice": self.generate_advice(emotion)
        }

        return report

    def generate_advice(self, emotion):

        primary = emotion["primary_emotion"]

        advice = {

            "happy": [
                "Keep your positive momentum.",
                "Share your success with others.",
                "Stay humble."
            ],

            "sad": [
                "Take a short break.",
                "Remember that setbacks are temporary.",
                "Focus on one small improvement."
            ],

            "fear": [
                "Prepare instead of worrying.",
                "Take one small action.",
                "Fear usually decreases after starting."
            ],

            "angry": [
                "Avoid making decisions immediately.",
                "Take a few minutes before responding.",
                "Think about the long-term outcome."
            ],

            "confident": [
                "Use your confidence wisely.",
                "Keep learning.",
                "Don't become overconfident."
            ],

            "neutral": [
                "Continue working steadily."
            ]
        }

        return advice.get(primary, ["No advice available."])