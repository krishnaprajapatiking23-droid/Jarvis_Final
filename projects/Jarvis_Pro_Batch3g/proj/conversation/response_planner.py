"""
==========================================
JARVIS PRO
Response Planner  (variation features 8, 9, 10, 13, 19, 23, 24, 26, 29, 30, 32)
==========================================

The decision layer that runs *before* the model is called.  For every turn
it decides:

  * what kind of turn this is - chat / factual / command / acknowledgement
  * how long the answer should be (explicit cues, emotion, style)
  * the user's apparent knowledge level
  * which structure to use, and which openings to avoid
  * whether this information was already given, and how long ago
  * whether this is a follow-up that must build on the last answer
  * which language to reply in
  * which generation parameters to use

Everything it produces is a *plan*, not a phrase.  The wording always
comes from the model.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from conversation import question_similarity as qs
from conversation import style_controller
from conversation.response_memory import response_memory

log = logging.getLogger("jarvis.conversation.planner")

# ------------------------------------------------------------------
# Explicit length cues (8)
# ------------------------------------------------------------------
ONE_LINE_CUES = (
    r"\bin one line\b", r"\bone line\b", r"\bone sentence\b",
    r"\bin a line\b", r"\bek line\b", r"\bone-liner\b",
)

SHORT_CUES = (
    r"\bquickly\b", r"\bquick\b", r"\bshort answer\b", r"\bshortly\b",
    r"\bbriefly\b", r"\bbrief\b", r"\bin short\b", r"\btl;?dr\b",
    r"\bsummar(y|ise|ize)\b", r"\bjust tell me\b", r"\bfast\b",
    r"\bchhota\b", r"\bjaldi\b",
)

DEEP_CUES = (
    r"\bin detail\b", r"\bdetailed\b", r"\bin depth\b", r"\bdeeply\b",
    r"\bgo deep\b", r"\bexplain properly\b", r"\bexplain fully\b",
    r"\btell me everything\b", r"\bfull explanation\b", r"\belaborate\b",
    r"\bthoroughly\b", r"\beverything about\b", r"\bcomplete detail\b",
    r"\bvistaar\b", r"\bpoori tarah\b",
)

EXAMPLE_CUES = (r"\bexample\b", r"\bfor instance\b", r"\bshow me\b", r"\budaharan\b")

# ------------------------------------------------------------------
# Knowledge level signals (9, 10)
# ------------------------------------------------------------------
BEGINNER_SIGNALS = (
    r"\bi'?m learning\b", r"\bi am learning\b", r"\bjust started\b",
    r"\bnew to\b", r"\bbeginner\b", r"\bnoob\b", r"\bsimple terms\b",
    r"\bexplain like i'?m\b", r"\beli5\b", r"\bdon'?t know anything\b",
    r"\bwhat does that mean\b", r"\bseekh raha\b", r"\bsamajh nahi\b",
)

ADVANCED_SIGNALS = (
    r"\bi'?m building\b", r"\bi am building\b", r"\bi'?m implementing\b",
    r"\barchitecture\b", r"\brefactor\b", r"\bthread(ing)?\b", r"\basync\b",
    r"\bconcurrenc\w+\b", r"\boptimi[sz]e\b", r"\bmemory leak\b",
    r"\bstack trace\b", r"\bdependency injection\b", r"\bschema\b",
    r"\bindex(es|ing)?\b", r"\bapi\b", r"\bsubprocess\b", r"\bembedding\b",
)

# ------------------------------------------------------------------
# Minimal-response turns (23, 24)
# ------------------------------------------------------------------
ACK_WORDS = {
    "ok", "okay", "okey", "k", "kk", "got it", "gotit", "gotcha",
    "understood", "i see", "isee", "cool", "nice", "great", "perfect",
    "awesome", "fine", "alright", "right", "sure", "hmm", "hm", "mmm",
    "acha", "achha", "accha", "theek hai", "thik hai", "thike",
    "samajh gaya", "samjh gaya", "ok done", "done",
}

THANKS_WORDS = {
    "thanks", "thank you", "thankyou", "thx", "ty", "tnx",
    "thanks a lot", "thank you so much", "shukriya", "dhanyawad",
    "thanks jarvis", "thank you jarvis",
}

PRAISE_WORDS = {
    "good job", "well done", "nice work", "good work", "great job",
    "perfect job", "you'?re the best", "badhiya", "shabash",
    # Single-word praise still deserves a one-line reply, not a paragraph.
    "nice", "great", "awesome", "cool", "perfect", "excellent", "superb",
    "amazing", "wow", "mast", "bahut badhiya",
}

# ------------------------------------------------------------------
# Factual / precise turns (29)
# ------------------------------------------------------------------
ARITHMETIC = re.compile(
    r"^\s*(?:what\s+is|whats|what's|calculate|compute|how much is|solve)?\s*"
    r"[-+]?\d+(?:\.\d+)?(?:\s*[-+*/x×÷^%]\s*[-+]?\d+(?:\.\d+)?)+\s*[=?]?\s*$",
    re.IGNORECASE,
)

PRECISE_PATTERNS = (
    r"\bwhat (?:is the )?time\b", r"\bwhat'?s the time\b",
    r"\btime kya\b", r"\bwhat(?:'s| is)? (?:today'?s )?date\b",
    r"\bwhich day\b", r"\bhow many days\b",
    r"\bwho (?:created|invented|founded|wrote|made)\b",
    r"\bwhen was .* (?:created|released|born|founded)\b",
    r"\bcapital of\b", r"\bhow old\b",
)

# ------------------------------------------------------------------
# Language detection (32)
# ------------------------------------------------------------------
HINGLISH_TOKENS = {
    "kya", "hai", "hain", "ho", "kaise", "kaisa", "kyun", "kyu", "kaha",
    "kahan", "kab", "batao", "bata", "samjhao", "mujhe", "mera", "meri",
    "tum", "aap", "nahi", "nahin", "haan", "acha", "achha", "thoda",
    "zara", "karo", "karna", "kar", "chalo", "bhai", "matlab", "theek",
    "thik", "bas", "abhi", "phir", "kuch", "sab", "bahut", "kaam",
}

DEVANAGARI = re.compile(r"[\u0900-\u097F]")

# Openings JARVIS should vary between (6) - used only as a "do not reuse"
# list for the model, never as a phrase bank to pick from.
DEPTHS = ("one_line", "short", "normal", "deep")


@dataclass
class ResponsePlan:
    """How this particular answer should be shaped."""

    question: str = ""
    kind: str = "chat"  # chat | factual | command | acknowledgement
    subtype: str = ""  # ack | thanks | praise
    depth: str = "normal"
    knowledge_level: str = "intermediate"
    language: str = "english"
    structure: str = ""
    opening_policy: str = "direct"
    tone: str = ""
    style: str = ""
    topic: str = ""
    project: str = ""
    factual: bool = False
    minimal: bool = False
    use_example: bool = False
    reference_previous: bool = False
    build_on_previous: bool = False
    previous_answer: str = ""
    repeat_count: int = 0
    same_session: bool = False
    fingerprint: str = ""
    diversity: str = "medium"
    avoid_openings: List[str] = field(default_factory=list)
    max_retries: int = 2
    revision: str = ""
    issues: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "question": self.question,
            "kind": self.kind,
            "subtype": self.subtype,
            "depth": self.depth,
            "knowledge_level": self.knowledge_level,
            "language": self.language,
            "structure": self.structure,
            "opening_policy": self.opening_policy,
            "tone": self.tone,
            "style": self.style,
            "topic": self.topic,
            "project": self.project,
            "factual": self.factual,
            "minimal": self.minimal,
            "use_example": self.use_example,
            "reference_previous": self.reference_previous,
            "build_on_previous": self.build_on_previous,
            "repeat_count": self.repeat_count,
            "same_session": self.same_session,
            "diversity": self.diversity,
            "avoid_openings": list(self.avoid_openings),
            "issues": list(self.issues),
        }


def _matches(patterns, text: str) -> bool:
    return any(re.search(pattern, text) for pattern in patterns)


def detect_depth(message: str, style: str = "", emotion: str = "") -> str:
    """How long the answer should be (8)."""
    lowered = (message or "").lower()

    if _matches(ONE_LINE_CUES, lowered):
        return "one_line"
    if _matches(DEEP_CUES, lowered):
        return "deep"
    if _matches(SHORT_CUES, lowered):
        return "short"

    if style in ("concise", "urgent"):
        return "short"
    if style in ("detailed", "explanatory", "technical"):
        return "deep"
    if emotion == "tired":
        return "short"

    # A bare "explain X" without a modifier is a normal-length answer.
    return "normal"


def detect_language(message: str) -> str:
    """english / hinglish / hindi (32)."""
    text = (message or "").strip()
    if not text:
        return "english"
    if DEVANAGARI.search(text):
        return "hindi"
    words = {word.strip(".,!?").lower() for word in text.split()}
    if words & HINGLISH_TOKENS:
        return "hinglish"
    return "english"


def detect_factual(message: str) -> bool:
    """True for questions with exactly one right answer (29)."""
    text = (message or "").strip()
    if not text:
        return False
    if ARITHMETIC.match(text):
        return True
    lowered = text.lower()
    return _matches(PRECISE_PATTERNS, lowered)


def detect_minimal(message: str) -> str:
    """'' | 'ack' | 'thanks' | 'praise' for throwaway turns (23, 24)."""
    cleaned = re.sub(r"[!.,?]+", " ", (message or "").lower())
    cleaned = re.sub(r"\bjarvis\b", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if not cleaned or len(cleaned.split()) > 4:
        return ""
    if cleaned in THANKS_WORDS:
        return "thanks"
    # Praise is checked before plain acknowledgement because words like
    # "nice" and "perfect" appear in both sets.
    if any(re.fullmatch(phrase, cleaned) for phrase in PRAISE_WORDS):
        return "praise"
    if cleaned in ACK_WORDS:
        return "ack"
    return ""


class KnowledgeTracker:
    """Tracks the user's apparent expertise per session (9, 10)."""

    def __init__(self) -> None:
        self._levels: Dict[str, str] = {}
        self._scores: Dict[str, int] = {}

    def observe(self, session_id: str, message: str) -> str:
        """Update the level from what the user just said."""
        key = session_id or "default"
        lowered = (message or "").lower()
        score = self._scores.get(key, 0)

        if _matches(BEGINNER_SIGNALS, lowered):
            score -= 2
        if _matches(ADVANCED_SIGNALS, lowered):
            score += 2

        score = max(-4, min(4, score))
        self._scores[key] = score

        if score <= -2:
            level = "beginner"
        elif score >= 2:
            level = "advanced"
        else:
            level = self._levels.get(key, "intermediate")

        self._levels[key] = level
        return level

    def level(self, session_id: str = "") -> str:
        return self._levels.get(session_id or "default", "intermediate")

    def set(self, session_id: str, level: str) -> None:
        self._levels[session_id or "default"] = level

    def clear(self) -> None:
        self._levels.clear()
        self._scores.clear()

    def reset(self, session_id: str = "") -> None:
        """Forget what we learned - for one session, or for all of them."""
        if not session_id:
            self.clear()
            return

        self._levels.pop(session_id, None)
        self._scores.pop(session_id, None)


knowledge_tracker = KnowledgeTracker()


def plan(
    message: str,
    understanding: Any = None,
    session_id: str = "",
    turn: int = 0,
    action: str = "",
) -> ResponsePlan:
    """Build the plan for this turn. Never raises."""
    text = (message or "").strip()

    emotion = str(getattr(understanding, "emotion", "") or "")
    style = str(getattr(understanding, "style", "") or "")
    topic = str(getattr(understanding, "topic", "") or "")
    intent = str(getattr(understanding, "intent", "") or "")
    references = getattr(understanding, "references", None) or []
    entities = getattr(understanding, "entities", None) or []

    if not session_id:
        session_id = str(getattr(understanding, "session_id", "") or "")
    if not turn:
        turn = int(getattr(understanding, "turn", 0) or 0)

    current_plan = ResponsePlan(
        question=text,
        topic=topic,
        tone=emotion if emotion and emotion != "neutral" else "",
        style=style,
        fingerprint=qs.fingerprint(text) if text else "",
        diversity=style_controller.level(),
    )

    try:
        # ---------- language (32) ----------
        current_plan.language = detect_language(text)

        # ---------- minimal turns (23, 24) ----------
        subtype = detect_minimal(text)
        if subtype:
            current_plan.kind = "acknowledgement"
            current_plan.subtype = subtype
            current_plan.minimal = True
            current_plan.depth = "one_line"
            current_plan.max_retries = 0
            return current_plan

        # ---------- factual precision (29) ----------
        if detect_factual(text):
            current_plan.kind = "factual"
            current_plan.factual = True
            current_plan.depth = detect_depth(text, style, emotion)
            if current_plan.depth == "normal":
                current_plan.depth = "short"
            current_plan.opening_policy = "none"
            current_plan.max_retries = 0
            return current_plan

        # ---------- commands (30) ----------
        if action and action not in ("chat", "conversation", "llm", ""):
            current_plan.kind = "command"
            current_plan.depth = "short"
            current_plan.opening_policy = "none"
            current_plan.max_retries = 0
            return current_plan

        # ---------- length (8) ----------
        current_plan.depth = detect_depth(text, style, emotion)

        # ---------- knowledge level (9, 10) ----------
        current_plan.knowledge_level = knowledge_tracker.observe(session_id, text)

        # ---------- already answered? (2, 4) ----------
        previous: Optional[Dict[str, Any]] = None
        if qs.is_question(text):
            previous = response_memory.previous(text, session_id)
        if previous:
            current_plan.previous_answer = str(previous.get("answer", ""))
            current_plan.repeat_count = int(previous.get("times_asked", 0) or 0)
            current_plan.same_session = bool(previous.get("same_session"))
            # Referencing the earlier answer is only natural when it was
            # recent; across sessions JARVIS just answers freshly (12).
            current_plan.reference_previous = (
                current_plan.same_session and int(previous.get("turns_ago", 99)) <= 12
            )

        # ---------- follow-up? (11) ----------
        short_question = len(text.split()) <= 8
        current_plan.build_on_previous = bool(
            not previous
            and turn > 1
            and (bool(references) or (short_question and bool(topic)))
        )

        # ---------- personalisation (13) ----------
        project = ""
        for entity in entities:
            if str(entity.get("type", "")).lower() == "project":
                project = str(entity.get("name", ""))
                break
        if not project:
            goal = str(getattr(understanding, "context", "") or "")
            match = re.search(r"Goal:\s*([^\n]+)", goal)
            if match:
                project = match.group(1).strip()
        current_plan.project = project

        # ---------- structure and openings (5, 6, 7) ----------
        current_plan.structure = style_controller.structure_for(
            current_plan.depth, response_memory.recent_structures()
        )
        current_plan.avoid_openings = response_memory.recent_openings(limit=3)

        # An opening phrase is allowed on explanatory turns, discouraged on
        # short ones, and never used when the user wants one line.
        if current_plan.depth == "one_line":
            current_plan.opening_policy = "none"
        elif current_plan.depth == "deep" or current_plan.repeat_count:
            current_plan.opening_policy = "natural"
        else:
            current_plan.opening_policy = "direct"

        current_plan.use_example = (
            _matches(EXAMPLE_CUES, text.lower())
            or (current_plan.depth == "deep" and current_plan.knowledge_level != "advanced")
        )

        if intent and intent not in ("chat", "question", "conversation"):
            current_plan.kind = "chat"

    except Exception as error:  # pragma: no cover - defensive
        log.warning("response planning failed: %s", error)

    return current_plan


__all__ = [
    "ResponsePlan",
    "KnowledgeTracker",
    "knowledge_tracker",
    "detect_depth",
    "detect_language",
    "detect_factual",
    "detect_minimal",
    "plan",
    "DEPTHS",
]
