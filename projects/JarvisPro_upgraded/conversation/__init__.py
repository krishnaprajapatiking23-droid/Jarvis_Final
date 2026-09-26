"""
==========================================
JARVIS PRO - Conversation System
==========================================

Context-aware conversation engine for JARVIS.

Quick use
---------
>>> from conversation import conversation_engine
>>> understanding = conversation_engine.understand("Open Chrome")
>>> reply = conversation_engine.commit(understanding, "Chrome is open.", "automation")

Modules
-------
``conversation_engine``   pipeline orchestrator
``context_manager``       context retrieval, ranking and assembly
``context_ranker``        relevance scoring and prompt assembly
``context_summarizer``    rolling conversation summaries
``conversation_state``    structured per-turn state
``session_manager``       session lifecycle and resumption
``history_manager``       persistence + intelligent retrieval
``store``                 SQLite layer (data/conversation.db)
``reference_resolver``    it / this / that / he / she / there
``topic_tracker``         topic tracking and switching
``entity_tracker``        people, companies, apps, places, projects
``temporal_parser``       today / tomorrow / in 10 minutes (local time)
``ambiguity_detector``    unsafe-to-guess detection
``clarification_manager`` smallest useful question
``correction_handler``    "no, I meant ..."
``emotion_detector``      confusion / frustration / excitement + style
``dialogue_manager``      greetings, farewells, natural composition
``dialogue_memory``       conversational facts
``incomplete_sentence``   unfinished input
``interruption``          stop / wait / cancel (voice aware)
``identity``              owner name from configuration

Legacy helpers that shipped with earlier JARVIS builds (``greetings``,
``history``, ``state``, ``personality``, ``context``, ``manager``, ...)
remain importable and unchanged.
"""

from __future__ import annotations

from conversation import store
from conversation.ambiguity_detector import ambiguity_detector
from conversation.clarification_manager import clarification_manager
from conversation.context_manager import context_manager
from conversation.context_ranker import context_ranker
from conversation.context_summarizer import context_summarizer
from conversation.conversation_engine import (
    ConversationEngine,
    Understanding,
    conversation_engine,
)
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
from conversation.session_manager import SessionManager, session_manager
from conversation.temporal_parser import temporal_parser
from conversation.topic_tracker import TopicTracker, topic_tracker

__all__ = [
    "ConversationEngine",
    "ConversationState",
    "SessionManager",
    "TopicTracker",
    "Understanding",
    "ambiguity_detector",
    "clarification_manager",
    "context_manager",
    "context_ranker",
    "context_summarizer",
    "conversation_engine",
    "correction_handler",
    "dialogue_manager",
    "dialogue_memory",
    "emotion_detector",
    "entity_tracker",
    "history_manager",
    "identity",
    "incomplete_sentence",
    "interruption_handler",
    "reference_resolver",
    "session_manager",
    "store",
    "temporal_parser",
    "topic_tracker",
]
