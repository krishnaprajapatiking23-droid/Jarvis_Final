"""
==========================================
JARVIS PRO
Conversation Engine
==========================================

The orchestrator for the whole Conversation System.  One call per turn:

    understanding = conversation_engine.understand(command)
    if understanding.handled:
        reply = understanding.handled_reply       # greeting, clarification, ...
    else:
        reply = <existing JARVIS brain / router produces a reply>
    reply = conversation_engine.commit(understanding, reply, action)

Pipeline implemented by ``understand()``
----------------------------------------
    input normalisation -> session detection -> interruption
    -> pending clarification -> session resume -> greeting / farewell
    -> correction -> incomplete sentence -> entity extraction
    -> reference resolution -> temporal parsing -> topic tracking
    -> ambiguity detection -> emotion & style -> dialogue memory
    -> intent detection -> context retrieval / ranking / summarisation

``commit()`` closes the loop: composition, state update, memory update and
history storage.

Every stage is individually guarded, so a failure in one feature degrades
that feature only - the assistant keeps working.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Dict, List, Optional

from conversation import store
from conversation.ambiguity_detector import ambiguity_detector
from conversation.clarification_manager import clarification_manager
from conversation.context_manager import context_manager
from conversation.conversation_state import ConversationState
from conversation.correction_handler import correction_handler
from conversation.dialogue_manager import dialogue_manager
from conversation.dialogue_memory import dialogue_memory
from conversation.emotion_detector import emotion_detector
from conversation.entity_tracker import entity_tracker
from conversation.history_manager import history_manager
from conversation.identity import identity
from conversation.incomplete_sentence import incomplete_sentence
from conversation.interruption import interruption_handler
from conversation.reference_resolver import reference_resolver
from conversation.session_manager import SessionManager
from conversation.temporal_parser import temporal_parser
from conversation.topic_tracker import TopicTracker

log = logging.getLogger("jarvis.conversation.engine")


@dataclass
class Understanding:
    """Everything the engine worked out about one user message."""

    original: str = ""
    text: str = ""
    command: str = ""

    session_id: str = ""
    conversation_id: str = ""
    turn: int = 0

    intent: str = ""
    entities: List[Dict[str, Any]] = field(default_factory=list)
    references: List[str] = field(default_factory=list)
    resolution: Dict[str, Any] = field(default_factory=dict)
    topic: str = ""
    topic_changed: bool = False
    topic_switched: bool = False
    temporal: Optional[Dict[str, Any]] = None
    correction: Dict[str, Any] = field(default_factory=dict)
    ambiguity: Dict[str, Any] = field(default_factory=dict)

    emotion: str = "neutral"
    confidence: float = 0.0
    style: str = ""
    repeated: bool = False

    incomplete: bool = False
    is_greeting: bool = False
    is_farewell: bool = False
    is_interruption: bool = False
    resumed: bool = False
    clarified: bool = False

    handled: bool = False
    handled_reply: str = ""
    ends_session: bool = False
    needs_llm: bool = True

    context: str = ""
    personality: str = ""
    tone: str = ""
    prefix: str = ""
    memories: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ConversationEngine:
    """Context-aware conversation orchestrator."""

    def __init__(
        self,
        mode: str = "text",
        llm: Optional[Callable[[str], str]] = None,
    ) -> None:
        self.mode = mode
        self.llm = llm
        self.sessions = SessionManager(mode=mode, user=identity.owner())
        self.topics = TopicTracker()
        self.context = context_manager
        self.context.llm = llm
        self.state = ConversationState()
        self.failures = 0
        self.last_understanding: Optional[Understanding] = None
        store.create_tables()

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    def normalize(self, text: str) -> str:
        """Trim, collapse whitespace and repair speech-recognition typos."""
        cleaned = " ".join((text or "").split())
        if not cleaned:
            return ""
        try:  # pragma: no cover - depends on host project state
            from brains_v2.correction import correction

            repaired = correction.correct(cleaned)
            if isinstance(repaired, str) and repaired.strip():
                cleaned = repaired.strip()
        except Exception as error:
            log.debug("stt correction unavailable: %s", error)
        return cleaned

    def detect_intent(self, text: str) -> str:
        """Reuse the existing intent detector; fall back to 'conversation'."""
        try:  # pragma: no cover - depends on host project state
            from brains_v2.intent import detect

            found = detect(text)
            if isinstance(found, str) and found:
                return found
        except Exception as error:
            log.debug("intent detector unavailable: %s", error)
        return "conversation"

    def _session(self) -> None:
        """Make sure a session exists and the state belongs to it."""
        session_id = self.sessions.ensure(mode=self.mode)
        if self.state.session_id != session_id:
            self.state = self.sessions.load_state()
            self.state.session_id = session_id
            self.state.conversation_id = self.sessions.conversation_id

    def _handled(self, understanding: Understanding, reply: str) -> Understanding:
        understanding.handled = True
        understanding.handled_reply = reply
        understanding.needs_llm = False
        return understanding

    # ------------------------------------------------------------------
    # main entry point
    # ------------------------------------------------------------------
    def understand(self, text: str, mode: str = "") -> Understanding:
        """Run the conversation pipeline for one user message."""
        if mode:
            self.mode = mode

        result = Understanding(original=text or "")
        self.last_understanding = result

        try:
            self._session()
        except Exception as error:  # pragma: no cover - defensive
            log.warning("session setup failed: %s", error)

        result.session_id = self.state.session_id
        result.conversation_id = self.state.conversation_id
        result.turn = self.sessions.next_turn()
        self.state.turn = result.turn

        message = self.normalize(text)
        result.text = message
        result.command = message

        # ---------- interruption (3.15) ----------
        # "Continue from where we stopped" asks to resume the previous
        # conversation (3.16), so that check owns the message instead.
        wants_resume = False
        try:
            wants_resume = self.sessions.is_resume_request(message)
        except Exception as error:  # pragma: no cover - defensive
            log.warning("resume check failed: %s", error)

        try:
            interrupt = interruption_handler.detect(message)
            if interrupt["interrupt"] and not wants_resume:
                result.is_interruption = True
                reply = interruption_handler.handle(interrupt["kind"], self.state)
                return self._handled(result, reply)
        except Exception as error:  # pragma: no cover - defensive
            log.warning("interruption check failed: %s", error)

        # ---------- answer to a pending clarification (3.25) ----------
        try:
            if self.state.is_waiting:
                answer = clarification_manager.resolve_answer(self.state, message)
                if answer and answer.get("status") == "resolved":
                    result.clarified = True
                    message = str(answer.get("command") or message)
                    result.text = message
                    result.command = message
                elif answer and answer.get("status") == "cancelled":
                    return self._handled(result, "Okay, cancelled.")
                elif self.state.pending_question and not answer:
                    self.state.clear_pending()
        except Exception as error:  # pragma: no cover - defensive
            log.warning("clarification handling failed: %s", error)

        if not message:
            report = incomplete_sentence.analyze(message)
            result.incomplete = True
            self.state.ask(report["question"])
            return self._handled(result, report["question"])

        # ---------- continue previous conversation (3.16) ----------
        try:
            if self.sessions.is_resume_request(message):
                previous = self.sessions.resume_context()
                if previous.get("found"):
                    result.resumed = True
                    reply = self.sessions.adopt(previous, self.state)
                    self.topics.current_topic = self.state.current_topic
                    return self._handled(result, reply)
                return self._handled(
                    result,
                    "I don't have an earlier conversation saved yet. "
                    "What would you like to start with?",
                )
        except Exception as error:  # pragma: no cover - defensive
            log.warning("resume handling failed: %s", error)

        # ---------- greeting (3.2) ----------
        try:
            if dialogue_manager.is_greeting(message):
                result.is_greeting = True
                result.intent = "greeting"
                returning = result.turn > 1
                reply = dialogue_manager.greeting_reply(
                    message, self.state, returning=returning
                )
                return self._handled(result, reply)
        except Exception as error:  # pragma: no cover - defensive
            log.warning("greeting check failed: %s", error)

        # ---------- farewell (3.3) ----------
        try:
            if dialogue_manager.is_farewell(message):
                result.is_farewell = True
                result.intent = "goodbye"
                result.ends_session = True
                reply = dialogue_manager.farewell_reply(message, self.state)
                return self._handled(result, reply)
        except Exception as error:  # pragma: no cover - defensive
            log.warning("farewell check failed: %s", error)

        # ---------- correction (3.23) ----------
        try:
            correction = correction_handler.detect(message, self.state)
            result.correction = correction
            if correction.get("is_correction"):
                rebuilt = str(correction.get("command") or "").strip()
                if rebuilt:
                    result.command = rebuilt
                    result.text = rebuilt
                result.prefix = correction_handler.acknowledge(correction)

                if correction.get("target") == "fact":
                    key = dialogue_memory.last_fact_key()
                    if key:
                        dialogue_memory.correct(key, str(correction.get("value", "")))
        except Exception as error:  # pragma: no cover - defensive
            log.warning("correction detection failed: %s", error)

        working = result.command

        # ---------- incomplete sentence (3.11) ----------
        try:
            # Clarification answers are checked as well, so
            # "Can you..." then "Open the..." asks again instead of
            # running half a command.
            if not result.correction.get("is_correction"):
                report = incomplete_sentence.analyze(working)
                if report["incomplete"]:
                    result.incomplete = True
                    self.state.ask(
                        report["question"],
                        {
                            "type": "clarification",
                            "original": working,
                            "action": report.get("verb", ""),
                            "reference": "",
                            "options": [],
                        },
                    )
                    return self._handled(result, report["question"])
        except Exception as error:  # pragma: no cover - defensive
            log.warning("incomplete sentence check failed: %s", error)

        # ---------- entity extraction (3.21) ----------
        try:
            found = entity_tracker.track(working)
            result.entities = found
            if found:
                self.state.remember_entities(found)
        except Exception as error:  # pragma: no cover - defensive
            log.warning("entity extraction failed: %s", error)

        # ---------- reference resolution (3.9, 3.10) ----------
        try:
            resolution = reference_resolver.resolve(working, self.state)
            result.resolution = resolution
            result.references = list(resolution.get("references") or [])
            if resolution.get("changed"):
                working = str(resolution.get("resolved") or working)
                result.command = working
            mapping = resolution.get("mapping") or {}
            if mapping:
                self.state.user_references.update(
                    {key: str(value) for key, value in mapping.items()}
                )
        except Exception as error:  # pragma: no cover - defensive
            log.warning("reference resolution failed: %s", error)

        # ---------- temporal understanding (3.22) ----------
        try:
            temporal = temporal_parser.parse(working)
            result.temporal = temporal
            if temporal:
                self.state.temporal = temporal
        except Exception as error:  # pragma: no cover - defensive
            log.warning("temporal parsing failed: %s", error)

        # ---------- topic tracking / switching (3.12, 3.13) ----------
        try:
            topic = self.topics.track(
                working,
                current=self.state.current_topic,
                has_reference=bool(result.references),
            )
            result.topic = str(topic.get("topic") or "")
            result.topic_changed = bool(topic.get("changed"))
            result.topic_switched = bool(topic.get("switched"))
            if result.topic:
                self.state.set_topic(result.topic)
        except Exception as error:  # pragma: no cover - defensive
            log.warning("topic tracking failed: %s", error)

        # ---------- ambiguity (3.24) + clarification (3.25) ----------
        try:
            ambiguity = ambiguity_detector.check(
                result.text,
                self.state,
                resolution=result.resolution,
                entities=result.entities,
            )
            result.ambiguity = ambiguity
            if ambiguity.get("ambiguous"):
                question = clarification_manager.ask(
                    self.state, ambiguity, result.text
                )
                return self._handled(result, question)
        except Exception as error:  # pragma: no cover - defensive
            log.warning("ambiguity detection failed: %s", error)

        # ---------- emotion & style (3.26 - 3.29) ----------
        try:
            repeated = history_manager.repeated_question(
                self.state.session_id, result.text
            )
            result.repeated = repeated
            emotion = emotion_detector.detect(
                result.text,
                repeated=repeated,
                failures=self.failures,
                previous=self.state.emotion,
            )
            result.emotion = str(emotion.get("emotion") or "neutral")
            result.confidence = float(emotion.get("confidence") or 0.0)
            result.style = str(emotion.get("style") or "")
            self.state.emotion = result.emotion
            if result.style:
                self.state.style = result.style
            elif emotion.get("needs_support"):
                self.state.style = "supportive"

            result.tone = " ".join(
                part
                for part in (
                    emotion_detector.tone_hint(result.emotion),
                    emotion_detector.style_hint(result.style or self.state.style),
                )
                if part
            ).strip()
        except Exception as error:  # pragma: no cover - defensive
            log.warning("emotion detection failed: %s", error)

        # ---------- dialogue memory (3.6) ----------
        try:
            answer = dialogue_memory.answer(result.text)
            if answer:
                result.intent = "memory"
                return self._handled(result, answer)
            fact = dialogue_memory.learn(result.text)
            if fact:
                result.intent = "memory"
        except Exception as error:  # pragma: no cover - defensive
            log.warning("dialogue memory failed: %s", error)

        # ---------- intent (reuse existing detector) ----------
        try:
            result.intent = result.intent or self.detect_intent(result.command)
        except Exception as error:  # pragma: no cover - defensive
            log.warning("intent detection failed: %s", error)
            result.intent = result.intent or "conversation"

        # ---------- context retrieval / ranking / summarisation ----------
        try:
            built = self.context.build(
                message=result.command,
                state=self.state,
                session_id=self.state.session_id,
                entities=result.entities,
                tone=result.tone,
            )
            result.context = str(built.get("context") or "")
            result.memories = list(built.get("memories") or [])
        except Exception as error:  # pragma: no cover - defensive
            log.warning("context building failed: %s", error)
            result.context = result.command

        try:
            result.personality = dialogue_manager.personality_prompt(
                style=emotion_detector.style_hint(result.style or self.state.style),
                tone=emotion_detector.tone_hint(result.emotion),
            )
        except Exception as error:  # pragma: no cover - defensive
            log.warning("personality prompt failed: %s", error)

        self.state.last_user_intent = result.intent
        return result

    # ------------------------------------------------------------------
    def prompt(self, understanding: Understanding) -> str:
        """Full structured prompt: personality + context + current message."""
        blocks = [
            understanding.personality,
            understanding.context or understanding.command,
        ]
        return "\n\n".join(block for block in blocks if block).strip()

    def current_context(self) -> str:
        """Structured prompt for the turn currently being processed.

        The LLM prompt builder calls this so the model receives ranked
        context instead of a raw history dump. Returns "" when there is
        no active turn.
        """
        understanding = self.last_understanding
        if understanding is None:
            return ""
        try:
            return self.prompt(understanding)
        except Exception as error:  # pragma: no cover - defensive
            log.debug("prompt build failed: %s", error)
            return ""

    # ------------------------------------------------------------------
    def commit(
        self,
        understanding: Understanding,
        reply: str,
        action: str = "",
        success: bool = True,
    ) -> str:
        """Compose the final reply, then persist state, memory and history.

        Returns the reply that should actually be spoken/printed.
        """
        final = (reply or "").strip()

        try:
            if understanding.prefix and final:
                # A correction acknowledgement replaces other decoration.
                if not final.lower().startswith(understanding.prefix[:6].lower()):
                    final = f"{understanding.prefix} {final}"
            elif understanding.prefix:
                final = understanding.prefix
            elif not understanding.handled:
                final = dialogue_manager.compose(
                    final,
                    self.state,
                    message=understanding.text,
                    emotion=understanding.emotion,
                    confidence=understanding.confidence,
                    style=understanding.style or self.state.style,
                    action=action,
                )
        except Exception as error:  # pragma: no cover - defensive
            log.warning("reply composition failed: %s", error)
            final = (reply or "").strip()

        # A model-unavailable status must not become part of the
        # conversation: it would be summarised, repeated and treated as a
        # previous answer on the next turn.
        # ---------- FINAL_USER_RESPONSE gate ----------
        # Everything the user sees leaves through here, so leaked
        # reasoning, prompt sections, debug text and raw payloads
        # are stopped in one place instead of eight.
        try:
            from conversation.output_sanitizer import final_user_response

            gated = final_user_response(final)

            if gated.final_text:
                final = gated.final_text

            elif gated.leaked:
                log.warning(
                    "internal content blocked for %r",
                    understanding.text,
                )
                final = (
                    "Sorry - I lost the thread of that one. "
                    "Could you ask me again?"
                )
                success = False

        except Exception as error:  # pragma: no cover - defensive
            log.warning("response gate failed: %s", error)

        try:
            from conversation.response_quality import is_unavailable

            failed_generation = is_unavailable(final)
        except Exception:  # pragma: no cover - defensive
            failed_generation = False

        if failed_generation:
            success = False
            log.warning("generation unavailable for %r", understanding.text)

        self.failures = 0 if success else self.failures + 1

        # ---------- state update (3.18) ----------
        try:
            self.state.last_user_message = understanding.text
            self.state.last_jarvis_reply = "" if failed_generation else final
            self.state.last_jarvis_action = action or understanding.intent
            if understanding.handled and not understanding.ambiguity.get("ambiguous"):
                if not understanding.incomplete:
                    self.state.clear_pending()
            self.sessions.save_state(self.state)
        except Exception as error:  # pragma: no cover - defensive
            log.warning("state update failed: %s", error)

        # ---------- history storage (3.4) ----------
        try:
            session_id = self.state.session_id
            history_manager.add(
                session_id,
                "user",
                understanding.text,
                conversation_id=self.state.conversation_id,
                turn=understanding.turn,
                intent=understanding.intent,
                topic=self.state.current_topic,
                emotion=understanding.emotion,
                entities=understanding.entities,
            )
            if final:
                history_manager.add(
                    session_id,
                    "jarvis",
                    final,
                    conversation_id=self.state.conversation_id,
                    turn=understanding.turn,
                    intent=action or understanding.intent,
                    topic=self.state.current_topic,
                )
        except Exception as error:  # pragma: no cover - defensive
            log.warning("history storage failed: %s", error)

        # ---------- entity / topic persistence (3.17, 3.21) ----------
        try:
            for entity in understanding.entities:
                store.upsert_entity(
                    self.state.session_id,
                    str(entity.get("name", "")),
                    str(entity.get("type", "")),
                    aliases=[str(entity.get("text", ""))],
                    context=str(entity.get("context", "")),
                )
            if self.state.current_topic:
                store.upsert_topic(self.state.session_id, self.state.current_topic)
                store.touch_session(
                    self.state.session_id, active_topic=self.state.current_topic
                )
        except Exception as error:  # pragma: no cover - defensive
            log.warning("entity/topic persistence failed: %s", error)

        # ---------- session end (3.3, 3.17) ----------
        if understanding.ends_session:
            try:
                self.end()
            except Exception as error:  # pragma: no cover - defensive
                log.warning("session close failed: %s", error)

        # ---------- response memory (variation 4, 18) ----------
        # Remember what was actually said so the next answer to the same
        # question can be phrased differently instead of replayed.
        try:
            if final:
                from conversation.response_memory import response_memory

                response_memory.record(
                    understanding.text,
                    final,
                    session_id=self.state.session_id,
                    turn=understanding.turn,
                    topic=self.state.current_topic,
                )
        except Exception as error:  # pragma: no cover - defensive
            log.debug("response memory update failed: %s", error)

        return final

    # ------------------------------------------------------------------
    def end(self) -> Dict[str, Any]:
        """Close the conversation session, saving a final summary."""
        session_id = self.state.session_id
        summary = self.state.summary
        try:
            transcript = store.recent_messages(session_id, limit=40)
            if transcript:
                summary = self.context.summarizer.summarize(
                    transcript, summary, use_llm=False
                )
        except Exception as error:  # pragma: no cover - defensive
            log.warning("final summary failed: %s", error)

        report = self.sessions.end(summary)
        history_manager.clear_cache(session_id)
        self.state = ConversationState()
        self.topics.clear()
        return report

    # ------------------------------------------------------------------
    def info(self) -> Dict[str, Any]:
        """Diagnostics for the manager/status commands."""
        data = self.sessions.info()
        data.update(
            {
                "topic": self.state.current_topic,
                "previous_topic": self.state.previous_topic,
                "emotion": self.state.emotion,
                "style": self.state.style,
                "entities": len(self.state.recent_entities),
                "pending_question": self.state.pending_question,
                "summary": bool(self.state.summary),
            }
        )
        return data


conversation_engine = ConversationEngine()

__all__ = ["ConversationEngine", "conversation_engine", "Understanding"]
