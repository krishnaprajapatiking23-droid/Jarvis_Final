"""
==========================================
JARVIS PRO
Dialogue Manager  (features 3.2, 3.3, 3.5, 3.14)
==========================================

Decides HOW to answer once the pipeline has worked out WHAT the user meant.

Responsibilities
----------------
  * greetings and farewells (3.2, 3.3) with time-of-day awareness
  * personality-consistent phrasing without hardcoding the user's name (3.5)
  * natural composition (3.14): never stack prefix + starter + follow-up +
    ending, never repeat the previous answer, length matched to the request

Composition is context aware.  Each decoration (name, tone opener,
follow-up question) is applied only when the conversation state justifies
it, and at most ONE decoration is added per reply.
"""

from __future__ import annotations

import difflib
import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from conversation.conversation_state import ConversationState
from conversation.identity import identity

log = logging.getLogger("jarvis.conversation.dialogue")

_ROTATION: Dict[tuple, int] = {}


def _pick(options) -> str:
    """Least-recently-used rotation instead of ``random.choice``.

    Variation has to be contextual and controlled, not random, so these
    short conversational lines now cycle predictably instead of being
    drawn at random on every turn.  Substantive answers never come from
    here - they come from the model via conversation/response_generator.py.
    """

    items = list(options)

    if not items:
        return ""

    key = tuple(items)
    index = _ROTATION.get(key, -1) + 1
    _ROTATION[key] = index
    return items[index % len(items)]


_STEPS: Dict[str, int] = {}
_STEP_FILE = Path(__file__).resolve().parent.parent / "data" / "dialogue_rotation.json"
_STEPS_LOADED = False
_PERSIST = True


def _load_steps() -> None:
    """Restore the counters saved by the previous run.

    Without this the counters restart at zero every time JARVIS starts,
    so the first greeting of every session would always be the same
    line.  The file is tiny and a failure to read or write it is never
    allowed to affect the conversation.
    """
    global _STEPS_LOADED

    if _STEPS_LOADED:
        return

    _STEPS_LOADED = True

    if not _PERSIST:
        return

    try:
        if _STEP_FILE.exists():
            with _STEP_FILE.open("r", encoding="utf-8") as handle:
                saved = json.load(handle)
            if isinstance(saved, dict):
                for name, value in saved.items():
                    if isinstance(name, str) and isinstance(value, int):
                        _STEPS[name] = value
    except Exception as error:  # pragma: no cover - defensive
        log.debug("rotation state could not be read: %s", error)


def _save_steps() -> None:
    if not _PERSIST:
        return

    try:
        _STEP_FILE.parent.mkdir(parents=True, exist_ok=True)
        with _STEP_FILE.open("w", encoding="utf-8") as handle:
            json.dump(_STEPS, handle)
    except Exception as error:  # pragma: no cover - defensive
        log.debug("rotation state could not be saved: %s", error)


def _step(name: str) -> int:
    """Next step number for a composed reply family (greeting, farewell).

    Each part of the reply reads this one counter with a different
    stride, so the *combination* changes every turn even though each
    individual pool is small.  The counter survives a restart, so the
    first "hello" of a new session does not repeat the first "hello" of
    the previous one.
    """
    _load_steps()
    value = _STEPS.get(name, -1) + 1
    _STEPS[name] = value
    _save_steps()
    return value


def reset_rotation(persist: bool = False) -> None:
    """Clear composition counters (used by tests).

    ``persist=False`` keeps tests off the on-disk counter file so a test
    run cannot change what the running assistant says next.
    """
    global _STEPS_LOADED, _PERSIST

    _PERSIST = bool(persist)
    _STEPS_LOADED = True
    _ROTATION.clear()
    _STEPS.clear()

# ------------------------------------------------------------------
# greetings (3.2)
# ------------------------------------------------------------------
GREETINGS = {
    "hello", "hi", "hii", "hiii", "hey", "heya", "yo", "hola",
    "namaste", "namaskar", "salaam",
    "good morning", "good afternoon", "good evening",
    "morning", "afternoon", "evening",
    "kya haal hai", "kaise ho", "kaisa hai", "kem cho",
    "how are you", "how are you doing", "how's it going", "hows it going",
    "what's up", "whats up", "sup",
    "are you there", "you there", "you awake", "wake up",
}

WELLBEING = {
    "how are you",
    "how are you doing",
    "how's it going",
    "hows it going",
    "kya haal hai",
    "kaise ho",
    "kaisa hai",
    "kem cho",
    "what's up",
    "whats up",
    "sup",
}

# ------------------------------------------------------------------
# farewells (3.3)
# ------------------------------------------------------------------
FAREWELLS = {
    "bye", "byee", "bye bye", "goodbye", "good bye",
    "good night", "goodnight", "nighty night",
    "see you", "see ya", "see you later", "see you soon",
    "talk to you later", "ttyl", "catch you later",
    "i'm leaving", "im leaving", "i am leaving", "i'm off", "im off",
    "i'm going", "im going", "i have to go", "gotta go",
    "that's all", "thats all", "that is all", "that's all for now",
    "nothing else", "we're done", "were done", "we are done",
    "stop talking", "exit", "quit", "log off", "shut down conversation",
    "alvida", "chalta hoon", "shubh ratri", "good night jarvis",
}

SLEEP_WORDS = {"good night", "goodnight", "shubh ratri", "nighty night", "good night jarvis"}

ASSISTANT_TOKENS = ("jarvis", "javis", "jarvis pro")

# Words that only address the assistant and carry no request.
ADDRESS_FILLERS = {"there", "buddy", "friend", "sir", "mate", "bro"}

# ------------------------------------------------------------------
# Greeting composition (3.2, 3.14)
# ------------------------------------------------------------------
# A greeting never reaches the model (it must answer instantly and must
# not be treated as a command), so variation here is *compositional*:
# one opener + an optional name + an optional second line, each part
# advanced by its own counter with a different stride.  That produces
# hundreds of distinct greetings from a handful of natural parts, and no
# greeting repeats until the whole cycle has been used - which is very
# different from picking a full canned sentence at random.

TIME_OPENERS = (
    "Good {part}.",
    "Good {part}.",
)

CASUAL_OPENERS = (
    "Hey.",
    "Hi.",
    "Hello.",
    "Hey there.",
    "Hi again.",
    "Yes?",
    "I'm here.",
    "Right here.",
    "Online.",
    "Listening.",
    "Still here.",
    "At your service.",
)

OFFERS = (
    "How can I help you today?",
    "What can I do for you?",
    "What are we working on?",
    "What's the plan?",
    "Where do we start?",
    "What do you need?",
    "Ready when you are.",
    "What's next on the list?",
    "Anything you want me to run?",
    "What are we building today?",
    "Go ahead.",
    "Tell me what you need.",
    "Say the word.",
)

WELLBEING_REPLIES = (
    "I'm running well, thanks for asking.",
    "All systems normal.",
    "Doing fine and ready to work.",
    "No issues on my side.",
    "Everything is running smoothly.",
    "Good - everything is responsive.",
    "Sab badhiya hai.",
    "Fine, and steady.",
)

FAREWELL_LINES = (
    "Goodbye. I'll be here when you need me.",
    "See you later.",
    "Talk to you soon.",
    "Catch you later.",
    "Take care.",
    "I'll be right here.",
    "Until next time.",
    "Bye for now.",
)

NIGHT_LINES = (
    "Good night. Sleep well.",
    "Good night.",
    "Good night - rest well.",
    "Shubh ratri.",
)

CLOSING_LINES = (
    "Alright, wrapping up.",
    "Okay, we're done for now.",
    "Closing this out then.",
    "Understood - stopping here.",
)

# The name appears roughly every fourth greeting instead of every one.
NAME_EVERY = 4

# A second line (offer) is skipped on some turns so greetings differ in
# shape as well as wording.
OFFER_SKIP = 3

# Openers used when the user's emotion warrants acknowledgement (3.26-3.28).
EMOTION_OPENERS: Dict[str, tuple[str, ...]] = {
    "frustrated": (
        "I understand - let me fix that.",
        "Understood. Let me correct that.",
    ),
    "confused": (
        "No problem, I'll put it more simply.",
        "Let me explain that differently.",
    ),
    "excited": ("Glad that worked.", "Nice."),
    "sad": ("Sorry to hear that.",),
    "tired": ("Keeping it short then.",),
    "angry": ("Understood.",),
}

# Follow-up questions are only offered on knowledge-style turns.
FOLLOW_UPS = (
    "Want me to go deeper on any part?",
    "Should I show an example?",
    "Want the details?",
)

QUESTION_WORDS = (
    "what", "who", "why", "how", "when", "where", "which",
    "tell me", "explain", "describe", "difference",
)

# One follow-up question at most every N turns.
FOLLOW_UP_EVERY = 4


def part_of_day(now: Optional[datetime] = None) -> str:
    """morning / afternoon / evening / night for the local clock."""
    hour = (now or datetime.now()).hour
    if 5 <= hour < 12:
        return "morning"
    if 12 <= hour < 17:
        return "afternoon"
    if 17 <= hour < 21:
        return "evening"
    return "night"


def _clean(text: str) -> str:
    """Lowercase, strip punctuation and the assistant's own name."""
    if not text:
        return ""
    lowered = text.strip().lower()
    lowered = re.sub(r"[!?.,]+", " ", lowered)
    for token in ASSISTANT_TOKENS:
        lowered = re.sub(rf"\b{token}\b", " ", lowered)
    lowered = re.sub(r"\b(please|okay|ok)\b", " ", lowered)
    lowered = re.sub(r"\s+", " ", lowered).strip()

    # "hey" is filler in "hey open Chrome" but the greeting itself in
    # "hey" or "hey there", so it is only dropped when something
    # meaningful follows it.
    words = lowered.split()
    if "hey" in words:
        rest = [word for word in words if word != "hey"]
        if rest and any(word not in ADDRESS_FILLERS for word in rest):
            words = rest
        lowered = " ".join(words)

    return re.sub(r"\s+", " ", lowered).strip()


class DialogueManager:
    """Greeting/farewell handling and natural reply composition."""

    def __init__(self) -> None:
        self._turns_since_follow_up = FOLLOW_UP_EVERY

    # ------------------------------------------------------------------
    # detection
    # ------------------------------------------------------------------
    def is_greeting(self, text: str) -> bool:
        """True only when the message is *purely* a greeting.

        "Good morning Jarvis"        -> greeting
        "Good morning, open Chrome"  -> not a greeting; the command runs
        """
        cleaned = _clean(text)
        if not cleaned:
            return False
        if cleaned in GREETINGS:
            return True
        # Allow a greeting plus a filler word, e.g. "hello there".
        words = cleaned.split()
        if len(words) <= 3:
            for phrase in GREETINGS:
                if cleaned.startswith(phrase):
                    remainder = cleaned[len(phrase) :].strip()
                    if remainder in ("", "there", "buddy", "friend", "sir"):
                        return True
        return False

    def is_wellbeing_question(self, text: str) -> bool:
        cleaned = _clean(text)
        return any(cleaned.startswith(phrase) for phrase in WELLBEING)

    def is_farewell(self, text: str) -> bool:
        cleaned = _clean(text)
        if not cleaned:
            return False
        if cleaned in FAREWELLS:
            return True
        words = cleaned.split()
        if len(words) <= 4:
            for phrase in FAREWELLS:
                if cleaned.startswith(phrase):
                    return True
        return False

    def is_sleep_farewell(self, text: str) -> bool:
        cleaned = _clean(text)
        return any(word in cleaned for word in SLEEP_WORDS)

    # ------------------------------------------------------------------
    # greeting / farewell replies
    # ------------------------------------------------------------------
    @staticmethod
    def _with_name(text: str, name: str) -> str:
        """Attach the owner's name naturally: "Good morning, Krishna."."""
        text = (text or "").strip()
        if not name or not text:
            return text
        if text.endswith((".", "!", "?")):
            return f"{text[:-1]}, {name}{text[-1]}"
        return f"{text}, {name}."

    def _greeting_opener(self, cleaned: str, step: int) -> str:
        """One opener, mirroring the user's own greeting when they used one.

        "good morning" is always mirrored (ignoring that would feel wrong),
        and so is "namaste".  Everything else alternates between a
        time-of-day opener and a casual one, so "hello" does not always
        come back as "Good <part of day>".
        """
        if cleaned.startswith("good ") and len(cleaned.split()) > 1:
            return f"Good {cleaned.split()[1]}."

        if cleaned in ("namaste", "namaskar"):
            return "Namaste."

        if cleaned in ("salaam",):
            return "Salaam."

        # Even steps -> time-of-day, odd steps -> casual.
        if step % 2 == 0:
            return f"Good {part_of_day()}."

        return CASUAL_OPENERS[(step // 2) % len(CASUAL_OPENERS)]

    def greeting_reply(
        self,
        text: str,
        state: Optional[ConversationState] = None,
        returning: bool = False,
    ) -> str:
        """Natural greeting response, composed fresh on every turn.

        The parts (opener / name / offer) each advance on their own
        counter, so repeating "hello" ten times produces ten different
        greetings without a canned list of full sentences and without
        random selection.
        """
        cleaned = _clean(text)
        step = _step("greeting")
        owner = identity.owner()

        # The name is used occasionally, not on every single greeting.
        name = owner if owner and step % NAME_EVERY == 0 else ""

        if self.is_wellbeing_question(text):
            reply = self._with_name(
                WELLBEING_REPLIES[step % len(WELLBEING_REPLIES)], name
            )
            if step % OFFER_SKIP == 0:
                return reply
            return f"{reply} {OFFERS[(step * 5) % len(OFFERS)]}".strip()

        opener = self._with_name(self._greeting_opener(cleaned, step), name)

        # A second line is added on most - but not all - greetings, and
        # mid-conversation greetings stay shorter than the first one.
        offer_step = OFFER_SKIP + 1 if returning else OFFER_SKIP
        if step % offer_step == 0:
            return opener

        return f"{opener} {OFFERS[(step * 5) % len(OFFERS)]}".strip()

    def farewell_reply(self, text: str, state: Optional[ConversationState] = None) -> str:
        """Graceful conversation ending, varied the same way."""
        step = _step("farewell")
        owner = identity.owner()
        name = owner if owner and step % NAME_EVERY == 0 else ""

        if self.is_sleep_farewell(text):
            return self._with_name(NIGHT_LINES[step % len(NIGHT_LINES)], name)

        cleaned = _clean(text)
        if cleaned.startswith(("that's all", "thats all", "that is all", "nothing else")):
            return self._with_name(CLOSING_LINES[step % len(CLOSING_LINES)], name)

        return self._with_name(FAREWELL_LINES[step % len(FAREWELL_LINES)], name)

    # ------------------------------------------------------------------
    # emotional acknowledgement
    # ------------------------------------------------------------------
    def emotion_opener(self, emotion: str, confidence: float = 0.0) -> str:
        """One short phrase acknowledging a detected emotion, or ""."""
        if not emotion or emotion == "neutral":
            return ""
        if confidence < 0.4:
            return ""
        options = EMOTION_OPENERS.get(emotion)
        return _pick(options) if options else ""

    # ------------------------------------------------------------------
    # natural composition (3.14)
    # ------------------------------------------------------------------
    def _is_knowledge_turn(self, message: str) -> bool:
        lowered = (message or "").lower()
        return lowered.endswith("?") or any(
            lowered.startswith(word) for word in QUESTION_WORDS
        )

    def _repeats_previous(self, reply: str, previous: str) -> bool:
        if not reply or not previous:
            return False
        if len(reply) < 25:
            return False
        ratio = difflib.SequenceMatcher(
            None, reply.strip().lower(), previous.strip().lower()
        ).ratio()
        return ratio > 0.85

    def compose(
        self,
        reply: str,
        state: ConversationState,
        message: str = "",
        emotion: str = "neutral",
        confidence: float = 0.0,
        style: str = "",
        action: str = "",
    ) -> str:
        """Apply at most one contextual decoration to ``reply``.

        Order of preference:
          1. emotional acknowledgement (when the emotion is clear)
          2. the user's name (only occasionally)
          3. a follow-up question (only on knowledge turns, spaced out)

        Automation confirmations, urgent/concise styles and clarification
        questions are returned untouched.
        """
        text = (reply or "").strip()
        if not text:
            return text

        try:
            # A model-unavailable status is a technical failure report, not
            # an answer.  Decorating it produced the reported nonsense
            # ("As I mentioned, empty response received from Ollama.",
            # "Understood. Let me correct that. Empty response ...").
            from conversation.response_quality import is_unavailable

            if is_unavailable(text):
                return text

            # Never decorate a question we are asking the user.
            if text.endswith("?") and state.pending_question:
                return text

            if self._repeats_previous(text, state.last_jarvis_reply):
                text = f"As I mentioned, {text[0].lower()}{text[1:]}"

            if style in ("concise", "urgent"):
                self._turns_since_follow_up += 1
                return text

            opener = self.emotion_opener(emotion, confidence)
            if opener:
                self._turns_since_follow_up += 1
                return f"{opener} {text}"

            # Action confirmations stay bare; they are already short.
            if action and action not in ("chat", "conversation", ""):
                self._turns_since_follow_up += 1
                return text

            name = identity.address()
            if name:
                self._turns_since_follow_up += 1
                if text.endswith((".", "!", "?")):
                    return f"{text[:-1]}, {name}{text[-1]}"
                return f"{text}, {name}."

            self._turns_since_follow_up += 1
            if (
                self._turns_since_follow_up >= FOLLOW_UP_EVERY
                and self._is_knowledge_turn(message)
                and not text.endswith("?")
                and len(text) > 80
                and not state.pending_question
            ):
                self._turns_since_follow_up = 0
                return f"{text} {_pick(FOLLOW_UPS)}"

            return text
        except Exception as error:  # pragma: no cover - defensive
            log.warning("reply composition failed: %s", error)
            return reply

    # ------------------------------------------------------------------
    def personality_prompt(self, style: str = "", tone: str = "") -> str:
        """System/personality block, reusing the project's personality data."""
        name = identity.owner()
        assistant = identity.assistant()

        lines = [
            f"You are {assistant}, a personal AI assistant.",
            "Be direct, warm and natural. Professional but not stiff.",
            "Answer the question actually asked, at a length that fits it.",
            "Do not repeat the user's words back to them.",
            "Do not start with filler such as 'Sure' or 'Certainly'.",
            "Do not end every reply with an offer of further help.",
        ]
        if name:
            lines.append(
                f"You are speaking with {name}. Use the name rarely, "
                "never in every reply."
            )

        try:  # pragma: no cover - depends on host project state
            from personality.personality import get_personality  # type: ignore

            extra = get_personality()
            if isinstance(extra, str) and extra.strip():
                lines.append(extra.strip())
        except Exception:
            pass

        if tone:
            lines.append(tone)
        if style:
            lines.append(style)

        return "\n".join(lines)


dialogue_manager = DialogueManager()

__all__ = [
    "DialogueManager",
    "dialogue_manager",
    "GREETINGS",
    "FAREWELLS",
    "part_of_day",
]
