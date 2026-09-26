"""
====================================================
Jarvis Human Intelligence System (JHIS)
Communication Module V2
Author : Jarvis Project
====================================================
"""

from dataclasses import dataclass
from typing import List


# -------------------------------
# Conversation Stages
# -------------------------------

STAGES = {

    "opening": [
        "hi",
        "hello",
        "hey",
        "good morning",
        "good evening",
        "good afternoon"
    ],

    "small_talk": [
        "how are you",
        "how was your day",
        "what's up",
        "what are you doing",
        "how is school",
        "how have you been"
    ],

    "rapport": [
        "tell me about yourself",
        "where are you from",
        "what do you like",
        "what are your hobbies",
        "favorite",
        "family"
    ],

    "deep": [
        "future",
        "dream",
        "goal",
        "life",
        "purpose",
        "career",
        "success",
        "fear"
    ],

    "closing": [
        "bye",
        "goodbye",
        "see you",
        "take care",
        "good night"
    ]

}


# -------------------------------
# Dataclass
# -------------------------------

@dataclass
class ConversationReport:

    stage: str

    confidence: int

    suggestions: List[str]

    friendliness: int

    engagement: int


# -------------------------------
# Stage Detection
# -------------------------------

def detect_stage(text: str):

    text = text.lower()

    scores = {}

    for stage, words in STAGES.items():

        scores[stage] = 0

        for word in words:

            if word in text:
                scores[stage] += 1

    best = max(scores, key=scores.get)

    if scores[best] == 0:
        return "unknown"

    return best


# -------------------------------
# Suggestions
# -------------------------------

def suggest(stage):

    data = {

        "opening": [
            "Smile while greeting.",
            "Ask an open-ended question.",
            "Use the person's name if known."
        ],

        "small_talk": [
            "Ask about their day.",
            "Avoid yes/no questions.",
            "Keep the tone light."
        ],

        "rapport": [
            "Find common interests.",
            "Listen more than you speak.",
            "Show curiosity."
        ],

        "deep": [
            "Respect personal opinions.",
            "Avoid interrupting.",
            "Ask thoughtful questions."
        ],

        "closing": [
            "End positively.",
            "Thank them.",
            "Leave the door open for another conversation."
        ],

        "unknown": [
            "Need more conversation."
        ]

    }

    return data.get(stage, ["Need more information."])


# -------------------------------
# Friendliness Score
# -------------------------------

def friendliness_score(stage):

    scores = {

        "opening": 70,

        "small_talk": 80,

        "rapport": 90,

        "deep": 95,

        "closing": 85,

        "unknown": 50

    }

    return scores.get(stage, 50)


# -------------------------------
# Engagement Score
# -------------------------------

def engagement_score(stage):

    scores = {

        "opening": 60,

        "small_talk": 70,

        "rapport": 85,

        "deep": 95,

        "closing": 40,

        "unknown": 30

    }

    return scores.get(stage, 30)


# -------------------------------
# Main Analyzer
# -------------------------------

def analyze(text):

    stage = detect_stage(text)

    confidence = 90 if stage != "unknown" else 20

    report = ConversationReport(

        stage=stage,

        confidence=confidence,

        suggestions=suggest(stage),

        friendliness=friendliness_score(stage),

        engagement=engagement_score(stage)

    )

    return report