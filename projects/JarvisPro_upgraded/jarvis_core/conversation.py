"""Section 3 - conversation signals, ambiguity detection and adaptive style.

What this gives the rest of Jarvis:

* ``ConversationEngine.analyse(text)`` returns a real :class:`Turn` analysis:
  detected signals (confusion / frustration / excitement / urgency / casual /
  technical), whether the request is ambiguous, which referents it depends on,
  and the style Jarvis should answer with.
* ``needs_clarification`` + ``clarification`` produce a *useful* question that
  lists the actual candidate targets instead of "what do you mean?".
* Signals are smoothed over a window, so one exclamation mark does not make
  Jarvis think the user is excited, and one "no" does not make it apologise
  forever ("do not overreact to every message").
* Everything is persisted per session in SQLite so the GUI, voice and Android
  surfaces observe the same conversation state after a restart.

Storage: ``data/conversation.db`` (``sessions``, ``turns``).
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

_DEF_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")

SIGNALS = ("confused", "frustrated", "excited", "urgent", "casual", "technical", "neutral")

# Pronouns / determiners that need a referent before the request is actionable.
REFERENTS = ("it", "this", "that", "those", "these", "there", "him", "her", "them", "the file",
             "the app", "the same", "again")

_PATTERNS: Dict[str, Sequence[str]] = {
    "confused": (r"\bi (don't|do not|dont) (get|understand)\b", r"\bwhat do you mean\b",
                 r"\bconfus(ed|ing)\b", r"\bhow does (that|this) work\b", r"\bi'?m lost\b",
                 r"\bmakes no sense\b"),
    "frustrated": (r"\b(still|again) (not|isn'?t) working\b", r"\bthis is (broken|useless|stupid)\b",
                   r"\bwhy (is|does|isn'?t) (it|this)\b", r"\bi already (told|said)\b",
                   r"\bnot what i asked\b", r"\bfor the (third|fourth|last) time\b", r"\bugh\b",
                   r"\b(still|again) (broken|failing|crashing)\b", r"\bnothing works\b",
                   r"\b(useless|pointless|garbage)\b", r"\bbroken again\b"),
    "excited": (r"\b(awesome|amazing|perfect|brilliant|love it|great job|wow)\b",
                r"\bcan'?t wait\b", r"\bthis is (so )?(cool|great)\b"),
    "urgent": (r"\b(asap|right now|immediately|hurry|urgent|quick(ly)?)\b", r"\bbefore \d",
               r"\bdeadline\b"),
    "casual": (r"\b(yo|hey|sup|lol|haha|bro|dude|thanks|thx)\b", r"\b(ok|okay) cool\b"),
    "technical": (r"\b(traceback|stack ?trace|exception|sqlite|regex|api|thread|deadlock|latency"
                  r"|docker|venv|dependency|commit|branch|json|http[s]?)\b", r"\b[a-z_]+\.py\b",
                  r"\b[A-Za-z]+Error\b"),
}

# Each style is a concrete instruction set the responder can honour.
STYLES: Dict[str, Dict[str, Any]] = {
    "standard": {"tone": "warm-professional", "verbosity": "balanced", "technical_depth": "medium",
                 "pace": "normal", "offer_help": False},
    "teaching": {"tone": "patient", "verbosity": "detailed", "technical_depth": "low",
                 "pace": "slow", "offer_help": True},
    "repair": {"tone": "direct-apologetic", "verbosity": "concise", "technical_depth": "medium",
               "pace": "fast", "offer_help": True},
    "celebratory": {"tone": "upbeat", "verbosity": "concise", "technical_depth": "medium",
                    "pace": "normal", "offer_help": False},
    "terse": {"tone": "neutral", "verbosity": "minimal", "technical_depth": "medium",
              "pace": "fast", "offer_help": False},
    "engineering": {"tone": "peer-engineer", "verbosity": "balanced", "technical_depth": "high",
                    "pace": "normal", "offer_help": False},
    "friendly": {"tone": "friendly", "verbosity": "concise", "technical_depth": "low",
                 "pace": "normal", "offer_help": False},
}

# signal -> style, checked in priority order (a frustrated technical user gets
# the repair style, not the engineering style).
_STYLE_PRIORITY: Sequence[Tuple[str, str]] = (
    ("frustrated", "repair"),
    ("confused", "teaching"),
    ("urgent", "terse"),
    ("excited", "celebratory"),
    ("technical", "engineering"),
    ("casual", "friendly"),
)

CONFIRM_THRESHOLD = 0.45  # a signal must clear this smoothed score to change behaviour


def _utc() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())


@dataclass
class Turn:
    turn_id: str
    session_id: str
    text: str
    signals: Dict[str, float] = field(default_factory=dict)
    dominant: str = "neutral"
    ambiguous: bool = False
    referents: List[str] = field(default_factory=list)
    candidates: List[str] = field(default_factory=list)
    clarification: Optional[str] = None
    style: str = "standard"
    style_directives: Dict[str, Any] = field(default_factory=dict)
    topic: Optional[str] = None
    created_at: str = field(default_factory=_utc)

    @property
    def needs_clarification(self) -> bool:
        return self.clarification is not None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "turn_id": self.turn_id, "session_id": self.session_id, "text": self.text,
            "signals": self.signals, "dominant": self.dominant, "ambiguous": self.ambiguous,
            "referents": self.referents, "candidates": self.candidates,
            "clarification": self.clarification, "style": self.style,
            "style_directives": self.style_directives, "topic": self.topic,
            "created_at": self.created_at,
        }


class ConversationEngine:
    def __init__(self, db_path: Optional[str] = None, window: int = 4,
                 personality: Any = None) -> None:
        os.makedirs(_DEF_DIR, exist_ok=True)
        self.db_path = db_path or os.path.join(_DEF_DIR, "conversation.db")
        self.window = max(1, window)
        self.personality = personality
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self) -> None:
        with self._lock:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    started_at TEXT,
                    last_seen TEXT,
                    surface TEXT,
                    topic TEXT,
                    state TEXT
                );
                CREATE TABLE IF NOT EXISTS turns (
                    turn_id TEXT PRIMARY KEY,
                    session_id TEXT,
                    text TEXT,
                    signals TEXT,
                    dominant TEXT,
                    ambiguous INTEGER,
                    referents TEXT,
                    candidates TEXT,
                    clarification TEXT,
                    style TEXT,
                    topic TEXT,
                    created_at TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_turns_session ON turns(session_id, created_at);
                """
            )
            self._conn.commit()

    # ---------------- sessions ----------------
    def start_session(self, surface: str = "text") -> str:
        session_id = "S-" + uuid.uuid4().hex[:10]
        with self._lock:
            self._conn.execute(
                "INSERT INTO sessions(session_id, started_at, last_seen, surface, topic, state)"
                " VALUES(?,?,?,?,?,?)",
                (session_id, _utc(), _utc(), surface, None, "active"),
            )
            self._conn.commit()
        return session_id

    def session(self, session_id: str) -> Dict[str, Any]:
        with self._lock:
            row = self._conn.execute("SELECT * FROM sessions WHERE session_id=?",
                                     (session_id,)).fetchone()
        if row is None:
            raise KeyError(f"unknown session {session_id}")
        return dict(row)

    def history(self, session_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM turns WHERE session_id=? ORDER BY rowid DESC LIMIT ?",
                (session_id, limit),
            ).fetchall()
        out = []
        for row in reversed(rows):
            item = dict(row)
            item["signals"] = json.loads(item["signals"] or "{}")
            item["referents"] = json.loads(item["referents"] or "[]")
            item["candidates"] = json.loads(item["candidates"] or "[]")
            item["ambiguous"] = bool(item["ambiguous"])
            out.append(item)
        return out

    # ---------------- signal detection ----------------
    def raw_signals(self, text: str) -> Dict[str, float]:
        """Per-message evidence score in 0..1 for each signal."""
        lowered = (text or "").lower()
        scores: Dict[str, float] = {}
        for signal, patterns in _PATTERNS.items():
            # count every match, not just every matching pattern: "quick! right now,
            # asap" is three pieces of evidence for urgency, not one.
            hits = sum(len(re.findall(p, lowered)) for p in patterns)
            if hits:
                scores[signal] = min(1.0, 0.45 + 0.25 * (hits - 1))
        # punctuation and shouting are weak evidence only
        exclaims = lowered.count("!")
        if exclaims >= 2:
            scores["excited"] = max(scores.get("excited", 0.0), 0.35)
        if text and len(text) > 8 and text.isupper():
            scores["frustrated"] = max(scores.get("frustrated", 0.0), 0.35)
        if lowered.count("?") >= 2:
            scores["confused"] = max(scores.get("confused", 0.0), 0.35)
        return scores

    def _smoothed(self, session_id: str, current: Dict[str, float]) -> Dict[str, float]:
        """Blend the current message with the recent window.

        A single weak hit stays below :data:`CONFIRM_THRESHOLD`; a repeated one
        crosses it. This is what stops Jarvis over-reacting to one sentence.
        """
        recent = self.history(session_id, self.window - 1) if self.window > 1 else []
        merged: Dict[str, float] = {}
        for signal in set(current) | {s for turn in recent for s in turn["signals"]}:
            now = current.get(signal, 0.0)
            past = [turn["signals"].get(signal, 0.0) for turn in recent]
            history_mean = sum(past) / len(past) if past else 0.0
            if not past:
                # nothing to smooth against: explicit evidence in the message itself
                # must not be diluted ("i'm confused" should register immediately).
                score = now
            else:
                # blend with the window, but never discount the current message by
                # more than 15% - smoothing damps noise, it does not ignore the user.
                score = max(0.85 * now, 0.7 * now + 0.3 * history_mean)
            # repetition is real evidence: two consecutive hits escalate
            if now > 0 and past and past[-1] > 0:
                score = min(1.0, score + 0.25)
            merged[signal] = round(score, 4)
        return merged

    # ---------------- ambiguity ----------------
    def detect_ambiguity(self, text: str, candidates: Sequence[str] = ()) -> Dict[str, Any]:
        lowered = f" {(text or '').lower().strip()} "
        found = [r for r in REFERENTS if re.search(rf"(?<![a-z]){re.escape(r)}(?![a-z])", lowered)]
        words = [w for w in re.findall(r"[a-z']+", lowered)]
        # "open it" / "do that" -> verb plus bare referent and nothing else
        bare = bool(found) and len(words) <= 4
        many_targets = len(candidates) > 1
        ambiguous = bool(found) and (bare or many_targets or not candidates)
        return {
            "ambiguous": ambiguous,
            "referents": found,
            "reason": ("unresolved referent(s) %s with %d candidate target(s)" % (found, len(candidates)))
            if ambiguous else "request is self-contained",
        }

    def clarify(self, text: str, candidates: Sequence[str] = ()) -> Optional[str]:
        """Build a useful clarification question, or None if none is needed."""
        info = self.detect_ambiguity(text, candidates)
        if not info["ambiguous"]:
            return None
        referent = info["referents"][0]
        if len(candidates) > 1:
            listed = ", ".join(candidates[:-1]) + f" or {candidates[-1]}"
            return f"When you say \u201c{referent}\u201d, do you mean {listed}?"
        if len(candidates) == 1:
            return f"Do you mean {candidates[0]}?"
        return f"I need one detail: what should \u201c{referent}\u201d refer to?"

    # ---------------- style ----------------
    def choose_style(self, signals: Dict[str, float], profile_pref: Optional[str] = None) -> str:
        confirmed = {s: v for s, v in signals.items() if v >= CONFIRM_THRESHOLD}
        for signal, style in _STYLE_PRIORITY:
            if signal in confirmed:
                return style
        if profile_pref in STYLES:
            return profile_pref
        return "standard"

    def directives(self, style: str) -> Dict[str, Any]:
        base = dict(STYLES.get(style, STYLES["standard"]))
        base["style"] = style
        if self.personality is not None:
            try:
                base.update(self.personality.constrain(base))
            except Exception:
                pass
        return base

    # ---------------- main entry ----------------
    def analyse(self, session_id: str, text: str, candidates: Sequence[str] = (),
                profile_pref: Optional[str] = None, topic: Optional[str] = None) -> Turn:
        if not isinstance(text, str) or not text.strip():
            raise ValueError("text must be a non-empty string")
        self.session(session_id)  # raises for unknown sessions instead of silently writing
        raw = self.raw_signals(text)
        signals = self._smoothed(session_id, raw)
        confirmed = {s: v for s, v in signals.items() if v >= CONFIRM_THRESHOLD}
        dominant = max(confirmed, key=confirmed.get) if confirmed else "neutral"
        amb = self.detect_ambiguity(text, candidates)
        style = self.choose_style(signals, profile_pref)
        turn = Turn(
            turn_id="T-" + uuid.uuid4().hex[:10],
            session_id=session_id,
            text=text,
            signals=signals,
            dominant=dominant,
            ambiguous=bool(amb["ambiguous"]),
            referents=list(amb["referents"]),
            candidates=list(candidates),
            clarification=self.clarify(text, candidates),
            style=style,
            style_directives=self.directives(style),
            topic=topic,
        )
        with self._lock:
            self._conn.execute(
                "INSERT INTO turns(turn_id, session_id, text, signals, dominant, ambiguous,"
                " referents, candidates, clarification, style, topic, created_at)"
                " VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (turn.turn_id, session_id, text, json.dumps(turn.signals), dominant,
                 int(turn.ambiguous), json.dumps(turn.referents), json.dumps(turn.candidates),
                 turn.clarification, style, topic, turn.created_at),
            )
            self._conn.execute("UPDATE sessions SET last_seen=?, topic=COALESCE(?, topic)"
                               " WHERE session_id=?", (_utc(), topic, session_id))
            self._conn.commit()
        return turn

    def mood(self, session_id: str) -> Dict[str, Any]:
        """Aggregate emotional context for the personality/GUI layers."""
        turns = self.history(session_id, self.window)
        if not turns:
            return {"dominant": "neutral", "signals": {}, "turns": 0}
        totals: Dict[str, float] = {}
        for turn in turns:
            for signal, value in turn["signals"].items():
                totals[signal] = totals.get(signal, 0.0) + value
        avg = {s: round(v / len(turns), 4) for s, v in totals.items()}
        confirmed = {s: v for s, v in avg.items() if v >= CONFIRM_THRESHOLD}
        return {
            "dominant": max(confirmed, key=confirmed.get) if confirmed else "neutral",
            "signals": avg,
            "turns": len(turns),
        }

    def close_session(self, session_id: str) -> None:
        with self._lock:
            self._conn.execute("UPDATE sessions SET state='closed', last_seen=? WHERE session_id=?",
                               (_utc(), session_id))
            self._conn.commit()


_ENGINE: Optional[ConversationEngine] = None
_ENGINE_LOCK = threading.RLock()


def get_conversation_engine(**kwargs: Any) -> ConversationEngine:
    global _ENGINE
    with _ENGINE_LOCK:
        if _ENGINE is None:
            _ENGINE = ConversationEngine(**kwargs)
        return _ENGINE
