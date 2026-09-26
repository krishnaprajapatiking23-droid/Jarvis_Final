"""
==========================================
JARVIS PRO
Emotion Detector  (features 3.26, 3.27, 3.28, 3.29)
==========================================

Detects the conversational mood behind a message:

  * confusion    - "what?", "what do you mean?", "I don't understand"
  * frustration  - "this isn't working", "I already told you"
  * excitement   - "wow!", "it worked!", "let's go!"
  * plus happy / sad / tired / angry

Scores are probabilistic and context aware: a short message is NOT treated
as frustration on its own, and frustration only fires once the signal is
strong enough or the same request has already failed.

It also picks the response style the user is asking for (3.29).
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List

log = logging.getLogger("jarvis.conversation.emotion")

NEUTRAL = "neutral"
CONFUSED = "confused"
FRUSTRATED = "frustrated"
EXCITED = "excited"
HAPPY = "happy"
SAD = "sad"
ANGRY = "angry"
TIRED = "tired"

# phrase -> weight
CONFUSION_SIGNALS: Dict[str, int] = {
    "what do you mean": 5,
    "i don't understand": 5,
    "i dont understand": 5,
    "i didn't understand": 5,
    "didn't get it": 4,
    "didnt get it": 4,
    "not clear": 3,
    "confusing": 4,
    "confused": 4,
    "huh": 4,
    "come again": 4,
    "say that again": 3,
    "explain again": 4,
    "kya matlab": 5,
    "samjha nahi": 5,
}

FRUSTRATION_SIGNALS: Dict[str, int] = {
    "this isn't working": 5,
    "this isnt working": 5,
    "it's not working": 5,
    "its not working": 5,
    "not working": 4,
    "doesn't work": 4,
    "doesnt work": 4,
    "why aren't you understanding": 6,
    "why arent you understanding": 6,
    "you're not listening": 6,
    "youre not listening": 6,
    "i already told you": 6,
    "i told you": 4,
    "again and again": 4,
    "how many times": 5,
    "useless": 5,
    "annoying": 4,
    "frustrating": 5,
    "still wrong": 5,
    "still not understanding": 6,
    "not understanding me": 6,
    "are not understanding": 6,
    "explained this": 5,
    "explained it": 5,
    "three times": 4,
    "four times": 4,
    "keep telling you": 6,
    "listen to me": 4,
    "wrong again": 5,
    "not what i asked": 6,
}

EXCITEMENT_SIGNALS: Dict[str, int] = {
    "wow": 4,
    "that's amazing": 5,
    "thats amazing": 5,
    "amazing": 3,
    "awesome": 4,
    "it worked": 5,
    "it works": 4,
    "finally": 4,
    "let's go": 5,
    "lets go": 5,
    "perfect": 3,
    "brilliant": 4,
    "excellent": 3,
    "love it": 4,
    "so cool": 4,
    "incredible": 4,
    "kamaal": 4,
}

HAPPY_SIGNALS: Dict[str, int] = {
    "thank you": 3,
    "thanks": 3,
    "good job": 4,
    "well done": 4,
    "happy": 3,
}

SAD_SIGNALS: Dict[str, int] = {
    "i'm sad": 5,
    "im sad": 5,
    "feeling low": 4,
    "depressed": 5,
    "unhappy": 4,
    "lonely": 4,
}

TIRED_SIGNALS: Dict[str, int] = {
    "i'm tired": 5,
    "im tired": 5,
    "exhausted": 5,
    "sleepy": 4,
    "no energy": 4,
}

ANGRY_SIGNALS: Dict[str, int] = {
    "shut up": 5,
    "i hate": 5,
    "angry": 4,
}

THRESHOLD = 4

# ------------------------------------------------------------------
# response style (3.29)
# ------------------------------------------------------------------
STYLE_SIGNALS: Dict[str, tuple[str, ...]] = {
    "concise": (
        "just tell me quickly",
        "quickly",
        "in short",
        "short answer",
        "be brief",
        "briefly",
        "one line",
        "tl;dr",
        "keep it short",
    ),
    "detailed": (
        "explain everything",
        "in detail",
        "detailed",
        "step by step",
        "elaborate",
        "full explanation",
        "tell me everything",
        "deep dive",
    ),
    "technical": (
        "technically",
        "technical details",
        "under the hood",
        "implementation",
        "architecture",
        "traceback",
        "stack trace",
        "exception",
        "async",
        "regex",
        "sql query",
        "time complexity",
        "source code",
    ),
    "beginner": (
        "like i'm five",
        "like im five",
        "simple words",
        "i'm a beginner",
        "im a beginner",
        "i am a beginner",
        "beginner friendly",
        "in simple terms",
        "easy explanation",
        "explain simply",
        "explain it simply",
        "keep it simple",
        "new to this",
        "never done this before",
        "eli5",
    ),
    "professional": (
        "formally",
        "professional tone",
        "for a client",
        "business tone",
    ),
    "casual": ("casually", "friendly tone", "talk normally"),
    "urgent": ("urgent", "asap", "right now", "immediately", "hurry"),
}

SUPPORT_TRIGGERS = (FRUSTRATED, SAD, TIRED, ANGRY)


def _score(text: str, signals: Dict[str, int]) -> tuple[int, List[str]]:
    total = 0
    hits: List[str] = []
    for phrase, weight in signals.items():
        if re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)", text):
            total += weight
            hits.append(phrase)
    return total, hits


class EmotionDetector:
    """Scores conversational emotion and preferred response style."""

    def detect(
        self,
        text: str,
        repeated: bool = False,
        failures: int = 0,
        previous: str = NEUTRAL,
    ) -> Dict[str, Any]:
        """Detect emotion for ``text``.

        ``repeated`` marks that the user just asked the same thing again and
        ``failures`` is the count of consecutive failed commands - both make
        frustration and confusion more likely without over-reacting to a
        single short message.

        Result::

            {"emotion": "frustrated", "confidence": 0.8, "scores": {...},
             "signals": [...], "style": "concise", "needs_support": True}
        """
        report: Dict[str, Any] = {
            "emotion": NEUTRAL,
            "confidence": 0.0,
            "scores": {},
            "signals": [],
            "style": "",
            "needs_support": False,
            "repeated": repeated,
        }

        if not text or not text.strip():
            return report

        try:
            lowered = text.strip().lower()
            stripped = lowered.rstrip("?!. ")

            scores: Dict[str, int] = {}
            signals: List[str] = []

            for emotion, table in (
                (CONFUSED, CONFUSION_SIGNALS),
                (FRUSTRATED, FRUSTRATION_SIGNALS),
                (EXCITED, EXCITEMENT_SIGNALS),
                (HAPPY, HAPPY_SIGNALS),
                (SAD, SAD_SIGNALS),
                (TIRED, TIRED_SIGNALS),
                (ANGRY, ANGRY_SIGNALS),
            ):
                score, hits = _score(lowered, table)
                if score:
                    scores[emotion] = score
                    signals.extend(hits)

            # Bare "what?" / "huh?" counts only as the entire message.
            if stripped in {"what", "huh", "eh", "sorry", "come again"}:
                scores[CONFUSED] = scores.get(CONFUSED, 0) + 4

            # Exclamation marks amplify excitement, not frustration.
            if "!" in text and EXCITED in scores:
                scores[EXCITED] += text.count("!")

            # ALL CAPS on a real sentence signals intensity.
            words = text.split()
            if (
                len(words) >= 2
                and text.upper() == text
                and any(character.isalpha() for character in text)
            ):
                boost = FRUSTRATED if FRUSTRATED in scores else EXCITED
                scores[boost] = scores.get(boost, 0) + 3

            # Context: repeats and failures push toward frustration.
            if repeated:
                scores[FRUSTRATED] = scores.get(FRUSTRATED, 0) + 2
                scores[CONFUSED] = scores.get(CONFUSED, 0) + 1
            if failures >= 2:
                scores[FRUSTRATED] = scores.get(FRUSTRATED, 0) + failures
            if previous == FRUSTRATED and scores.get(FRUSTRATED):
                scores[FRUSTRATED] += 1

            report["scores"] = scores
            report["signals"] = signals
            report["style"] = self.detect_style(lowered)

            if scores:
                emotion = max(scores, key=lambda key: scores[key])
                best = scores[emotion]
                if best >= THRESHOLD:
                    report["emotion"] = emotion
                    report["confidence"] = round(min(best / 10.0, 1.0), 2)

            report["needs_support"] = report["emotion"] in SUPPORT_TRIGGERS
            return report
        except Exception as error:  # pragma: no cover - defensive
            log.warning("emotion detection failed: %s", error)
            return report

    # ------------------------------------------------------------------
    def detect_style(self, lowered: str) -> str:
        """Explicit style request in the message, or "" when none."""
        for style, phrases in STYLE_SIGNALS.items():
            for phrase in phrases:
                if phrase in lowered:
                    return style
        return ""

    # ------------------------------------------------------------------
    def tone_hint(self, emotion: str) -> str:
        """Instruction fragment used when building the model prompt."""
        return {
            FRUSTRATED: (
                "The user is frustrated. Stay calm, skip pleasantries, "
                "acknowledge the problem briefly and fix it."
            ),
            CONFUSED: (
                "The user is confused. Re-explain the last point more simply "
                "and concretely, without repeating it word for word."
            ),
            EXCITED: (
                "The user is excited. Match the energy in one short phrase, "
                "then continue normally."
            ),
            SAD: "The user sounds low. Be warm and brief.",
            TIRED: "The user is tired. Be brief and easy to read.",
            ANGRY: "The user is annoyed. Be direct, no filler, no jokes.",
            HAPPY: "The user is pleased. Keep it light and short.",
        }.get(emotion, "")

    # ------------------------------------------------------------------
    def style_hint(self, style: str) -> str:
        return {
            "concise": "Answer in one or two short sentences. No preamble.",
            "detailed": "Give a thorough, structured explanation.",
            "technical": "Use precise technical language and specifics.",
            "beginner": "Explain simply, avoid jargon, use a small example.",
            "professional": "Use a polished, professional tone.",
            "casual": "Use a relaxed, conversational tone.",
            "urgent": "Lead with the answer or action. Be extremely brief.",
            "supportive": "Be reassuring and practical.",
        }.get(style, "")


emotion_detector = EmotionDetector()

__all__ = [
    "EmotionDetector",
    "emotion_detector",
    "CONFUSED",
    "FRUSTRATED",
    "EXCITED",
    "NEUTRAL",
    "STYLE_SIGNALS",
]
