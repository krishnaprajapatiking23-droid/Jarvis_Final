"""Tests for the Jarvis Conversation System (features 3.1 - 3.29).

Every test builds a fresh :class:`ConversationEngine` on a throwaway SQLite
file, so the real ``data/conversation.db`` is never touched and the tests can
run in any order.

The file is plain ``pytest`` (assert based, no fixtures required), so it also
runs with ``python tools/run_tests.py`` when pytest is not installed.
"""

import os
import sys
import tempfile
from datetime import datetime, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from conversation import store
from conversation.context_ranker import MAX_CONTEXT_CHARS
from conversation.context_summarizer import SUMMARY_EVERY
from conversation.conversation_engine import ConversationEngine
from conversation.dialogue_memory import dialogue_memory
from conversation.entity_tracker import entity_tracker
from conversation.history_manager import history_manager
from conversation.identity import identity
from conversation.reference_resolver import REFERENCE_WORDS
from conversation.temporal_parser import temporal_parser

STYLES = {
    "concise",
    "detailed",
    "technical",
    "beginner",
    "beginner-friendly",
    "professional",
    "casual",
    "supportive",
    "urgent",
    "explanatory",
    "neutral",
}


# ----------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------
def engine():
    """Fresh engine backed by an isolated database."""

    folder = tempfile.mkdtemp(prefix="jarvis-conversation-")
    store.use_database(os.path.join(folder, "conversation.db"))
    store.create_tables()
    entity_tracker.clear()
    dialogue_memory.clear()
    history_manager.clear_cache()
    identity.reset()
    return ConversationEngine(mode="text")


def temporal_list(value):
    """Normalise ``Understanding.temporal`` into a list of dicts."""

    if isinstance(value, dict):
        return [value]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    return []


def say(jarvis, command, reply, action=""):
    """Run one full turn and return the understanding plus the final reply."""

    understanding = jarvis.understand(command)
    if understanding.handled:
        return understanding, jarvis.commit(understanding, understanding.handled_reply)
    return understanding, jarvis.commit(understanding, reply, action)


# ----------------------------------------------------------------------
# 3.1 Basic conversation
# ----------------------------------------------------------------------
def test_basic_conversation_stores_the_turn():
    jarvis = engine()

    first = jarvis.understand("Who is Elon Musk?")
    assert first.session_id
    assert first.conversation_id
    assert first.turn == 1

    reply = jarvis.commit(first, "Elon Musk is an entrepreneur known for Tesla and SpaceX.")
    assert "entrepreneur" in reply

    assert store.message_count(first.session_id) == 2
    assert jarvis.state.last_user_message == "Who is Elon Musk?"
    assert jarvis.state.last_jarvis_reply


def test_basic_conversation_resolves_he():
    jarvis = engine()

    first = jarvis.understand("Who is Elon Musk?")
    jarvis.commit(first, "Elon Musk is an entrepreneur known for Tesla and SpaceX.")

    second = jarvis.understand("How old is he?")
    assert "he" in second.references
    assert "elon musk" in second.command.lower()


# ----------------------------------------------------------------------
# 3.2 Greetings
# ----------------------------------------------------------------------
def test_greeting_is_answered_not_executed():
    jarvis = engine()

    result = jarvis.understand("Good morning Jarvis.")
    assert result.is_greeting
    assert result.handled
    assert "good morning" in result.handled_reply.lower()
    assert result.intent != "automation"


def test_greeting_variants_are_recognised():
    jarvis = engine()

    for text in [
        "hello",
        "hi",
        "hey",
        "good afternoon",
        "good evening",
        "namaste",
        "kya haal hai",
        "kaise ho",
        "how are you",
    ]:
        result = jarvis.understand(text)
        assert result.handled, text
        assert result.handled_reply.strip(), text


# ----------------------------------------------------------------------
# 3.3 Goodbye
# ----------------------------------------------------------------------
def test_goodbye_closes_the_conversation():
    jarvis = engine()

    opening = jarvis.understand("Open Chrome")
    jarvis.commit(opening, "Chrome is open.", "automation")

    for text in ["bye", "goodbye", "see you", "talk to you later", "i'm leaving", "that's all"]:
        result = jarvis.understand(text)
        assert result.is_farewell, text
        assert result.handled, text

    farewell = jarvis.understand("good night")
    assert farewell.ends_session
    assert jarvis.commit(farewell, farewell.handled_reply).strip()

    finished = opening.session_id
    jarvis.end()
    fresh = jarvis.understand("Open Notepad")
    assert fresh.session_id != finished


# ----------------------------------------------------------------------
# 3.4 Conversation history
# ----------------------------------------------------------------------
def test_history_retrieval_returns_relevant_messages():
    jarvis = engine()

    say(jarvis, "Tell me about Python", "Python is a programming language.")
    for index in range(10):
        say(jarvis, f"Open Notepad number {index}", f"Notepad {index} is open.", "automation")

    session_id = jarvis.state.session_id
    assert store.message_count(session_id) == 22

    found = history_manager.relevant(session_id, "python")
    text = " ".join(item.get("text", "") for item in found).lower()
    assert "python" in text

    stored = store.recent_messages(session_id, limit=2)
    assert stored
    assert stored[-1].get("created_at") or stored[-1].get("timestamp")


# ----------------------------------------------------------------------
# 3.5 Personality
# ----------------------------------------------------------------------
def test_personality_does_not_repeat_the_owner_name():
    jarvis = engine()
    owner = identity.owner()

    replies = []
    for index in range(6):
        _, reply = say(jarvis, f"Explain python topic {index}", f"Answer {index}.")
        replies.append(reply)

    assert all(reply.strip() for reply in replies)
    if owner:
        assert sum(owner in reply for reply in replies) <= 2


# ----------------------------------------------------------------------
# 3.6 Dialogue memory
# ----------------------------------------------------------------------
def test_dialogue_memory_recalls_a_preference():
    jarvis = engine()

    say(jarvis, "My favorite programming language is Python.", "Noted.")

    question = jarvis.understand("What programming language do I like?")
    assert question.handled
    assert "python" in question.handled_reply.lower()


# ----------------------------------------------------------------------
# 3.7 Long conversations
# ----------------------------------------------------------------------
def test_long_conversation_keeps_the_thread():
    jarvis = engine()

    say(jarvis, "Tell me about Python", "Python is a programming language.")
    say(jarvis, "Who created it?", "Guido van Rossum created it.")
    say(jarvis, "When was it released?", "In 1991.")
    last, _ = say(jarvis, "Why was it created?", "To make code readable.")

    assert "python" in (jarvis.state.current_topic or "").lower()
    assert "python" in last.context.lower()
    assert len(last.context) <= MAX_CONTEXT_CHARS


# ----------------------------------------------------------------------
# 3.8 / 3.16 Long-term context and continuation
# ----------------------------------------------------------------------
def test_previous_session_can_be_continued():
    jarvis = engine()

    say(jarvis, "I was learning Python", "Good choice.")
    jarvis.end()

    resumed = jarvis.understand("Continue from where we stopped.")
    assert resumed.resumed
    assert "python" in (resumed.handled_reply + " " + resumed.context).lower()


def test_long_term_memory_survives_a_new_engine():
    jarvis = engine()

    say(jarvis, "My favorite editor is VS Code", "Noted.")
    jarvis.end()

    other = ConversationEngine(mode="text")
    answer = other.understand("What editor do I like?")
    assert "vs code" in (answer.handled_reply or "").lower()


# ----------------------------------------------------------------------
# 3.9 Follow-ups
# ----------------------------------------------------------------------
def test_follow_up_question_uses_the_topic():
    jarvis = engine()

    say(jarvis, "Tell me about Python", "Python is a programming language.")
    follow_up = jarvis.understand("Is it difficult?")
    assert "python" in follow_up.command.lower()


def test_next_action_keeps_the_context():
    jarvis = engine()

    say(jarvis, "Open Chrome", "Chrome is open.", "automation")
    second = jarvis.understand("Now open YouTube.")
    assert not second.handled
    names = [item["name"].lower() for item in second.entities]
    assert "youtube" in names


# ----------------------------------------------------------------------
# 3.10 Reference resolution
# ----------------------------------------------------------------------
def test_close_it_resolves_to_the_last_app():
    jarvis = engine()

    say(jarvis, "Open Notepad", "Notepad is open.", "automation")
    closing = jarvis.understand("Close it")
    assert "it" in closing.references
    assert "notepad" in closing.command.lower()


def test_reference_vocabulary_is_complete():
    for word in [
        "it",
        "this",
        "that",
        "these",
        "those",
        "there",
        "here",
        "he",
        "she",
        "they",
        "them",
        "his",
        "her",
        "its",
    ]:
        assert word in REFERENCE_WORDS, word


# ----------------------------------------------------------------------
# 3.11 Incomplete sentences
# ----------------------------------------------------------------------
def test_incomplete_sentences_ask_for_the_rest():
    jarvis = engine()

    can_you = jarvis.understand("Can you...")
    assert can_you.incomplete
    assert can_you.handled
    assert "what would you like me to do" in can_you.handled_reply.lower()

    open_the = jarvis.understand("Open the...")
    assert open_the.incomplete
    assert open_the.handled
    assert "?" in open_the.handled_reply

    dangling = jarvis.understand("Open Chrome and...")
    assert dangling.incomplete
    assert dangling.handled


# ----------------------------------------------------------------------
# 3.12 / 3.13 Topics
# ----------------------------------------------------------------------
def test_topic_tracking_narrows_the_subject():
    jarvis = engine()

    first, _ = say(jarvis, "Tell me about Python", "Python is a language.")
    second, _ = say(jarvis, "What libraries are useful?", "NumPy and Pandas.")
    third, _ = say(jarvis, "Which one is best for AI?", "PyTorch is popular.")

    assert "python" in first.topic.lower()
    assert "librar" in second.topic.lower()
    assert "python" in third.topic.lower()


def test_topic_switch_is_detected():
    jarvis = engine()

    say(jarvis, "Tell me about Python", "Python is a language.")
    switched, _ = say(jarvis, "By the way, what's the weather today?", "It is sunny.")

    assert switched.topic_switched or switched.topic_changed
    assert "weather" in switched.topic.lower()
    assert "python" in (jarvis.state.previous_topic or "").lower()


# ----------------------------------------------------------------------
# 3.14 Natural conversation
# ----------------------------------------------------------------------
def test_repeated_answers_are_not_repeated_verbatim():
    jarvis = engine()

    _, first = say(jarvis, "Tell me about Python", "Python is a programming language created in 1991.")
    _, second = say(jarvis, "Tell me about Python again", "Python is a programming language created in 1991.")

    assert second != first
    assert "mentioned" in second.lower()


# ----------------------------------------------------------------------
# 3.15 Interruption
# ----------------------------------------------------------------------
def test_interruption_is_short_and_stops_output():
    jarvis = engine()

    say(jarvis, "Tell me about Python", "Python is a programming language.")

    stop = jarvis.understand("wait")
    assert stop.is_interruption
    assert stop.handled
    assert len(stop.handled_reply) <= 40

    for text in ["stop", "hold on", "cancel", "never mind", "pause", "shut up", "that's enough"]:
        assert jarvis.understand(text).is_interruption, text


# ----------------------------------------------------------------------
# 3.17 Sessions
# ----------------------------------------------------------------------
def test_sessions_do_not_mix():
    jarvis = engine()

    first, _ = say(jarvis, "Open Chrome", "Chrome is open.", "automation")
    first_session = first.session_id
    jarvis.end()

    second, _ = say(jarvis, "Open Notepad", "Notepad is open.", "automation")

    assert second.session_id != first_session
    assert store.message_count(first_session) == 2
    assert store.message_count(second.session_id) == 2

    record = store.get_session(first_session)
    assert record
    assert record.get("started_at") or record.get("start_time")


# ----------------------------------------------------------------------
# 3.18 Conversation state
# ----------------------------------------------------------------------
def test_conversation_state_schema_and_persistence():
    jarvis = engine()

    understanding, _ = say(jarvis, "Open Chrome", "Chrome is open.", "automation")
    data = jarvis.state.to_dict()

    for key in [
        "current_topic",
        "previous_topic",
        "active_entities",
        "recent_entities",
        "conversation_goal",
        "last_user_intent",
        "last_jarvis_action",
        "pending_question",
        "pending_action",
        "user_references",
        "session_id",
        "conversation_id",
        "emotion",
        "style",
    ]:
        assert key in data, key

    assert data["last_jarvis_action"] == "automation"
    assert data["session_id"] == understanding.session_id
    assert store.load_state(understanding.session_id)


# ----------------------------------------------------------------------
# 3.19 / 3.20 Context window and summaries
# ----------------------------------------------------------------------
def test_context_window_is_bounded():
    jarvis = engine()

    for index in range(30):
        say(jarvis, f"Question {index} about python and chrome", f"Answer {index}.")

    last = jarvis.understand("And what about python?")
    assert len(last.context) <= MAX_CONTEXT_CHARS
    assert "Question 0 about python" not in last.context


def test_old_context_is_summarised():
    jarvis = engine()

    for index in range(SUMMARY_EVERY * 2 + 2):
        say(jarvis, f"My python project number {index} needs tests", f"Understood {index}.")

    summary = store.last_summary(jarvis.state.session_id)
    assert summary
    assert summary.get("summary", "").strip()


# ----------------------------------------------------------------------
# 3.21 Entities
# ----------------------------------------------------------------------
def test_entities_are_tracked_with_types():
    jarvis = engine()

    understanding, _ = say(
        jarvis,
        "Open Chrome and tell me about Tesla in Mumbai",
        "Done.",
        "automation",
    )

    names = [item["name"].lower() for item in understanding.entities]
    assert "chrome" in names

    rows = store.entities(understanding.session_id)
    assert rows
    assert "name" in rows[0]
    assert "type" in rows[0]


# ----------------------------------------------------------------------
# 3.22 Temporal understanding
# ----------------------------------------------------------------------
def test_temporal_expressions_use_local_time():
    today = datetime.now().date()

    assert temporal_parser.parse("today")["date"] == today.isoformat()
    assert temporal_parser.parse("tomorrow")["date"] == (today + timedelta(days=1)).isoformat()
    assert temporal_parser.parse("yesterday")["date"] == (today - timedelta(days=1)).isoformat()

    for text in [
        "tonight",
        "this morning",
        "next week",
        "last week",
        "in 10 minutes",
        "after 2 hours",
        "later",
        "earlier",
        "recently",
        "tomorrow morning",
    ]:
        assert temporal_parser.parse(text), text

    assert temporal_parser.parse("in 10 minutes").get("seconds") == 600
    assert temporal_parser.parse("after 2 hours").get("seconds") == 7200


def test_temporal_reference_reaches_the_understanding():
    jarvis = engine()

    understanding = jarvis.understand("Remind me to call mom tomorrow morning")
    stamps = temporal_list(understanding.temporal)
    assert stamps
    assert stamps[0].get("date") == (datetime.now().date() + timedelta(days=1)).isoformat()


# ----------------------------------------------------------------------
# 3.23 Corrections
# ----------------------------------------------------------------------
def test_correction_replaces_the_action_target():
    jarvis = engine()

    say(jarvis, "Open Chrome", "Opening Chrome.", "automation")

    fix = jarvis.understand("No, I meant Edge")
    assert fix.correction.get("is_correction")
    assert "edge" in fix.command.lower()
    assert "edge" in (fix.prefix + " " + (fix.handled_reply or "")).lower()


def test_correction_updates_a_remembered_fact():
    jarvis = engine()

    say(jarvis, "My favorite language is Java", "Noted.")
    say(jarvis, "Actually, I meant Python", "Updated.")

    question = jarvis.understand("What language do I like?")
    assert "python" in (question.handled_reply or "").lower()
    assert "java" not in (question.handled_reply or "").lower()


# ----------------------------------------------------------------------
# 3.24 / 3.25 Ambiguity and clarification
# ----------------------------------------------------------------------
def test_ambiguous_reference_is_detected():
    jarvis = engine()

    for app in ["Chrome", "Notepad", "Calculator"]:
        say(jarvis, f"Open {app}", f"{app} is open.", "automation")

    vague = jarvis.understand("Open it")
    assert vague.ambiguity.get("ambiguous")
    assert len(vague.ambiguity.get("options", [])) >= 2


def test_clarification_is_small_and_keeps_state():
    jarvis = engine()

    for app in ["Chrome", "Notepad"]:
        say(jarvis, f"Open {app}", f"{app} is open.", "automation")

    vague = jarvis.understand("Open it")
    assert vague.handled
    assert "?" in vague.handled_reply
    assert len(vague.handled_reply) < 80
    jarvis.commit(vague, vague.handled_reply)

    answer = jarvis.understand("Chrome")
    assert answer.clarified
    assert "chrome" in answer.command.lower()


def test_clear_requests_are_not_questioned():
    jarvis = engine()

    understanding = jarvis.understand("Open Chrome")
    assert not understanding.handled
    assert not understanding.ambiguity.get("ambiguous")


# ----------------------------------------------------------------------
# 3.26 - 3.28 Emotion
# ----------------------------------------------------------------------
def test_confusion_is_detected_and_softened():
    jarvis = engine()

    say(jarvis, "Tell me about decorators", "A decorator wraps a function.")

    confused = jarvis.understand("I don't understand")
    assert confused.emotion == "confused"

    reply = jarvis.commit(confused, "Here is a simpler explanation.")
    assert reply != "Here is a simpler explanation."


def test_frustration_detection_is_conservative():
    jarvis = engine()

    assert jarvis.understand("this isn't working").emotion == "frustrated"
    assert jarvis.understand("why aren't you understanding?").emotion == "frustrated"
    assert jarvis.understand("I already told you").emotion == "frustrated"

    assert jarvis.understand("ok").emotion == "neutral"
    assert jarvis.understand("open notepad").emotion == "neutral"


def test_excitement_detection():
    jarvis = engine()

    assert jarvis.understand("Wow! It worked!").emotion == "excited"
    assert jarvis.understand("Finally! Let's go!").emotion == "excited"
    assert jarvis.understand("open notepad").emotion != "excited"


# ----------------------------------------------------------------------
# 3.29 Adaptive style
# ----------------------------------------------------------------------
def test_style_adapts_to_the_request():
    jarvis = engine()

    assert jarvis.understand("Just tell me quickly").style == "concise"
    assert jarvis.understand("Explain everything in detail").style == "detailed"

    beginner = jarvis.understand("I am a beginner, explain simply").style
    assert beginner in STYLES

    technical = jarvis.understand("Show me the async traceback of this exception").style
    assert technical in STYLES


# ----------------------------------------------------------------------
# Combination scenario from the specification
# ----------------------------------------------------------------------
def test_combination_chrome_tutorials_tomorrow_today():
    jarvis = engine()

    say(jarvis, "Open Chrome.", "Chrome is open.", "automation")
    say(jarvis, "Search for Python tutorials.", "Searching for Python tutorials.", "browser")
    scheduled, _ = say(
        jarvis,
        "Actually search for beginner tutorials tomorrow.",
        "Scheduled the search for tomorrow.",
        "browser",
    )
    corrected, reply = say(
        jarvis,
        "No, I meant today.",
        "Searching for beginner tutorials today.",
        "browser",
    )

    state = str(jarvis.state.to_dict()).lower()
    assert "chrome" in state
    assert "tutorial" in (jarvis.state.current_topic or "").lower()

    assert scheduled.correction.get("is_correction")
    assert corrected.correction.get("is_correction")

    dates = [stamp.get("date") for stamp in temporal_list(corrected.temporal)]
    assert datetime.now().date().isoformat() in dates

    assert jarvis.state.last_user_intent
    assert store.message_count(jarvis.state.session_id) == 8
    assert reply.strip()


# ----------------------------------------------------------------------
# Robustness
# ----------------------------------------------------------------------
def test_empty_input_is_handled():
    jarvis = engine()

    result = jarvis.understand("   ")
    assert result.handled
    assert result.handled_reply.strip()


def test_database_failure_does_not_break_the_reply():
    jarvis = engine()
    original = store.add_message

    def broken(*args, **kwargs):
        raise RuntimeError("database offline")

    store.add_message = broken
    try:
        understanding = jarvis.understand("Open Chrome")
        reply = jarvis.commit(understanding, "Chrome is open.", "automation")
        assert "Chrome is open." in reply
    finally:
        store.add_message = original


def test_engine_reports_its_configuration():
    jarvis = engine()

    say(jarvis, "Open Chrome", "Chrome is open.", "automation")

    info = jarvis.info()
    assert info.get("session_id")
    assert "topic" in info
    assert "emotion" in info
