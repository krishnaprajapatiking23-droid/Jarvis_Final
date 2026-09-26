"""
=========================================================
Jarvis Human Intelligence System
Personal Coach V1
=========================================================
"""

from psychology.reasoning import PsychologyReasoner


class PersonalCoach:

    def __init__(self):
        self.reasoner = PsychologyReasoner()

    def coach(self, text):

        report = self.reasoner.analyze(text)

        emotion = report["emotion"]["primary_emotion"]

        plan = self.build_plan(emotion)

        return {
            "analysis": report,
            "action_plan": plan
        }

    def build_plan(self, emotion):

        plans = {

            "happy": [
                "Continue your current routine.",
                "Write today's success in your journal.",
                "Help someone else today."
            ],

            "sad": [
                "Take a 15-minute walk.",
                "Write down what went wrong.",
                "Identify one thing you can improve tomorrow."
            ],

            "fear": [
                "List the things you can control.",
                "Take one small action today.",
                "Prepare instead of overthinking."
            ],

            "angry": [
                "Wait before reacting.",
                "Take 10 deep breaths.",
                "Solve the problem, not the person."
            ],

            "confident": [
                "Use your confidence to learn something difficult.",
                "Set a bigger goal.",
                "Stay humble."
            ],

            "neutral": [
                "Keep following your routine.",
                "Review today's progress.",
                "Learn something new."
            ]

        }

        return plans.get(emotion, ["No recommendation available."])