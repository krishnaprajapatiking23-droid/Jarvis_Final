"""
==========================================
JARVIS PRO
Response Memory  (variation features 4, 18, 28, 33)
==========================================

Remembers *what JARVIS already said* so the next answer can be different.

This is not a second memory system: the durable copy of every message
already lives in ``conversation_messages`` (conversation/store.py).  This
module keeps a small in-process index over that data - question,
answer, structure used, opening used - and hydrates itself from the
database when the process restarts, which is what makes "same question in
a new session" work (test 4).

It deliberately stores answers only as *history*, never as a cache to
replay: ``previous()`` is used to avoid repeating an answer, not to serve
one (28).
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence

from conversation import question_similarity as qs
from conversation import repetition_detector

log = logging.getLogger("jarvis.conversation.response_memory")

# How many question/answer pairs to keep in the working index.
MAX_RECORDS = 80

# How many past sessions to hydrate from the database.
HYDRATE_SESSIONS = 5

# How many messages to read per hydrated session.
HYDRATE_MESSAGES = 40


class ResponseMemory:
    """Index of recent question/answer pairs with similarity lookup."""

    def __init__(self) -> None:
        self._records: List[Dict[str, Any]] = []
        self._hydrated = False

    # ------------------------------------------------------------------
    # writing
    # ------------------------------------------------------------------
    def record(
        self,
        question: str,
        answer: str,
        session_id: str = "",
        turn: int = 0,
        structure: str = "",
        topic: str = "",
    ) -> None:
        """Remember that ``answer`` was given to ``question``."""
        answer = (answer or "").strip()
        if not answer:
            return

        # The generator stores its own draft and the conversation engine
        # stores the committed reply for the same turn.  Without this guard
        # one exchange would be counted twice and inflate "asked N times".
        question_text = (question or "").strip()
        for existing in reversed(self._records[-4:]):
            if (
                existing["session_id"] == session_id
                and existing["turn"] == turn
                and existing["question"] == question_text
            ):
                existing["answer"] = answer
                existing["opening"] = repetition_detector.opening_of(answer)
                if structure:
                    existing["structure"] = structure
                if topic:
                    existing["topic"] = topic
                return

        record = {
            "question": (question or "").strip(),
            "answer": answer,
            "session_id": session_id,
            "turn": turn,
            "structure": structure,
            "topic": topic,
            "opening": repetition_detector.opening_of(answer),
            "fingerprint": qs.fingerprint(question) if question else "",
            "at": datetime.now().isoformat(timespec="seconds"),
        }
        self._records.append(record)
        if len(self._records) > MAX_RECORDS:
            del self._records[: len(self._records) - MAX_RECORDS]

    # ------------------------------------------------------------------
    # hydration from the conversation database
    # ------------------------------------------------------------------
    def hydrate(self, session_id: str = "", force: bool = False) -> int:
        """Load past question/answer pairs from storage. Returns the count.

        Failures are swallowed: response variation must never stop JARVIS
        from answering.
        """
        if self._hydrated and not force:
            return 0
        self._hydrated = True

        loaded = 0
        try:
            from conversation import store

            session_ids: List[str] = []
            if session_id:
                session_ids.append(session_id)
            for session in store.sessions(limit=HYDRATE_SESSIONS):
                identifier = str(session.get("session_id", ""))
                if identifier and identifier not in session_ids:
                    session_ids.append(identifier)

            for identifier in session_ids:
                messages = store.recent_messages(identifier, limit=HYDRATE_MESSAGES)
                pending_question = ""
                for message in messages:
                    role = str(message.get("role", ""))
                    text = str(message.get("text", "")).strip()
                    if not text:
                        continue
                    if role == "user":
                        pending_question = text
                    elif role in ("jarvis", "assistant") and pending_question:
                        self.record(
                            pending_question,
                            text,
                            session_id=identifier,
                            turn=int(message.get("turn", 0) or 0),
                            topic=str(message.get("topic", "") or ""),
                        )
                        loaded += 1
                        pending_question = ""
        except Exception as error:  # pragma: no cover - defensive
            log.debug("response memory hydration failed: %s", error)

        return loaded

    # ------------------------------------------------------------------
    # reading
    # ------------------------------------------------------------------
    def previous(
        self,
        question: str,
        session_id: str = "",
        threshold: float = qs.SIMILARITY_THRESHOLD,
    ) -> Optional[Dict[str, Any]]:
        """The most recent answer to this same information request, if any.

        Returns a dict with the answer, how many times the question has been
        asked, whether that was in this session, and how many turns ago.
        """
        if not question:
            return None

        self.hydrate(session_id)

        matches = [
            record
            for record in self._records
            if record.get("question")
            and qs.same_request(question, str(record["question"]), threshold)
        ]
        if not matches:
            return None

        latest = matches[-1]

        # The same exchange can reach memory twice (generator draft and the
        # engine's committed reply) and again from the database on hydrate,
        # so count each turn once.
        seen_turns = {
            (record.get("session_id", ""), record.get("turn", 0))
            for record in matches
        }

        return {
            "question": latest["question"],
            "answer": latest["answer"],
            "times_asked": len(seen_turns),
            "same_session": bool(session_id) and latest.get("session_id") == session_id,
            "turns_ago": max(0, len(self._records) - self._records.index(latest) - 1),
            "structure": latest.get("structure", ""),
            "session_id": latest.get("session_id", ""),
            "score": qs.similarity(question, str(latest["question"])),
        }

    def times_asked(self, question: str, session_id: str = "") -> int:
        """How often this information was requested before (0 if never)."""
        previous = self.previous(question, session_id)
        return int(previous["times_asked"]) if previous else 0

    def recent_answers(self, limit: int = 5) -> List[str]:
        """The last replies JARVIS gave, newest last."""
        return [str(record["answer"]) for record in self._records[-limit:]]

    def recent_openings(self, limit: int = 5) -> List[str]:
        """Normalised openings of the last replies."""
        openings = [str(record.get("opening", "")) for record in self._records[-limit:]]
        return [opening for opening in openings if opening]

    def recent_structures(self, limit: int = 4) -> List[str]:
        """Structures used for the last few substantial replies."""
        structures = [
            str(record.get("structure", "")) for record in self._records[-limit:]
        ]
        return [structure for structure in structures if structure]

    def answers_for(self, question: str, limit: int = 3) -> List[str]:
        """Every recent answer given to this same information request."""
        matches = [
            str(record["answer"])
            for record in self._records
            if record.get("question")
            and qs.same_request(question, str(record["question"]))
        ]
        return matches[-limit:]

    def all(self) -> Sequence[Dict[str, Any]]:
        return tuple(self._records)

    def count(self) -> int:
        return len(self._records)

    def clear(self) -> None:
        """Drop the index (used by tests and by session resets)."""
        self._records.clear()
        self._hydrated = False


response_memory = ResponseMemory()

__all__ = ["ResponseMemory", "response_memory", "MAX_RECORDS"]
