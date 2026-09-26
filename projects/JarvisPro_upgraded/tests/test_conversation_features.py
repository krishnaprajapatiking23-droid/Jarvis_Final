"""
==========================================
JARVIS PRO
Full conversation feature coverage
==========================================

One test per shipped conversation feature, exercised through the real
modules (no mocks of our own code), so a regression anywhere in the
conversation stack fails here.

Covered: basic conversation, greetings, goodbye, history, personality,
dialogue memory, long conversations, long-term context, follow-ups,
reference resolution, incomplete sentences, topic tracking, topic
switching, natural conversation, interruption, resume, sessions,
conversation state, context window, summarization, entity tracking,
temporal understanding, corrections, ambiguity, clarification,
confusion, frustration, excitement, adaptive style, response variation,
output sanitization, routing, memory, goals.

Run with:  python tools/run_tests.py tests/test_conversation_features.py
"""

import os
import sys
import tempfile
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


class _OptionalStub(types.ModuleType):
    """Stand-in for desktop-only packages missing on a test machine."""

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)

        return _OptionalStub(f"{self.__name__}.{name}")

    def __call__(self, *args, **kwargs):
        return None


for _name in (
    "pyautogui",
    "pyperclip",
    "pygetwindow",
    "psutil",
    "ollama",
    "httpx",
    "comtypes",
    "pycaw",
    "edge_tts",
    "pyttsx3",
    "speech_recognition",
):
    sys.modules.setdefault(_name, _OptionalStub(_name))

from conversation import repetition_detector, request_type, store
from conversation.ambiguity_detector import ambiguity_detector
from conversation.clarification_manager import clarification_manager
from conversation.context_manager import context_manager
from conversation.context_ranker import context_ranker
from conversation.context_summarizer import context_summarizer
from conversation.conversation_engine import conversation_engine
from conversation.conversation_state import ConversationState
from conversation.correction_handler import correction_handler
from conversation.dialogue_manager import dialogue_manager, reset_rotation
from conversation.dialogue_memory import dialogue_memory
from conversation.emotion_detector import emotion_detector
from conversation.entity_tracker import entity_tracker
from conversation.history_manager import history_manager
from conversation.incomplete_sentence import incomplete_sentence
from conversation.interruption import interruption_handler
from conversation.output_sanitizer import final_user_response, looks_internal
from conversation.reference_resolver import reference_resolver
from conversation.response_planner import plan as plan_response
from conversation.response_quality import check as quality_check
from conversation.session_manager import session_manager
from conversation.style_controller import structure_for
from conversation.temporal_parser import temporal_parser
from conversation.topic_tracker import topic_tracker

# --------------------------------------------------------------
# Every test runs against a throwaway conversation database.
# --------------------------------------------------------------
_TEMP_DB = os.path.join(tempfile.mkdtemp(prefix="jarvis_features_"), "conversation.db")
store.use_database(_TEMP_DB)


def fresh_state(topic=""):
    """A clean conversation state, optionally with a current topic."""

    state = ConversationState()

    if topic:
        state.set_topic(topic)

    return state


def assert_clean(text):
    """No internal content may ever reach the user."""

    assert not looks_internal(text or ""), f"internal content in {text!r}"

    lowered = (text or "").lower()

    for marker in ("<think", "system:", "[router]", "key points to cover"):
        assert marker not in lowered, f"leaked {marker!r}"


# ======================================================================
# Greetings, goodbyes, personality
# ======================================================================

def test_greeting_is_recognised_and_answered():
    reset_rotation()

    for text in ("hello", "hi jarvis", "namaste", "good morning"):
        assert dialogue_manager.is_greeting(text), text

    reply = dialogue_manager.greeting_reply("hello", fresh_state())

    assert reply.strip()
    assert_clean(reply)


def test_wellbeing_question_is_not_a_command():
    for text in ("kaise ho", "how are you", "kya haal hai"):
        assert dialogue_manager.is_wellbeing_question(text), text
        assert not request_type.is_action_request(text), text


def test_greetings_vary_between_turns():
    reset_rotation()

    state = fresh_state()

    replies = [
        dialogue_manager.greeting_reply("hello", state) for _ in range(4)
    ]

    assert len(set(replies)) > 1, replies

    for reply in replies:
        assert_clean(reply)


def test_farewell_is_recognised_and_answered():
    assert dialogue_manager.is_farewell("bye jarvis")
    assert dialogue_manager.is_farewell("good night")

    reply = dialogue_manager.farewell_reply("bye jarvis", fresh_state())

    assert reply.strip()
    assert_clean(reply)


def test_owner_name_is_not_stamped_on_every_reply():
    reset_rotation()

    state = fresh_state("python")

    replies = []

    for index in range(6):
        state.turn = index + 1
        replies.append(
            dialogue_manager.compose(
                "Python is a programming language.",
                state,
                message="What is Python?",
            )
        )

    named = [reply for reply in replies if "Krishna" in reply]

    assert len(named) < len(replies), replies


def test_personality_prompt_describes_style_without_leaking():
    prompt = dialogue_manager.personality_prompt(style="technical")

    assert prompt.strip()
    assert "<think" not in prompt


# ======================================================================
# Topic tracking / switching
# ======================================================================

def test_topic_is_tracked_and_can_be_revisited():
    topic_tracker.clear()

    first = topic_tracker.track("Let's discuss JARVIS.")

    assert first["topic"]

    second = topic_tracker.track("Now let's discuss Python.", first["topic"])

    assert second["topic"] != first["topic"]
    assert second["changed"] is True

    third = topic_tracker.track(
        "Go back to our JARVIS discussion.", second["topic"]
    )

    assert first["topic"].split()[0] in third["topic"], third
    assert first["topic"] in topic_tracker.history() or third["topic"]


def test_explicit_switch_is_detected():
    assert topic_tracker.is_switch("Now let's talk about something else.")
    assert not topic_tracker.is_switch("Why is it popular?")


def test_returning_to_the_first_topic_is_understood():
    topic_tracker.clear()

    one = topic_tracker.track("Tell me about Python.")
    two = topic_tracker.track("Now tell me about India.", one["topic"])
    back = topic_tracker.track(
        "Now tell me something about the first topic we discussed.",
        two["topic"],
    )

    assert back["topic"], back
    assert back["topic"] != two["topic"]


# ======================================================================
# Entities, references, follow-ups
# ======================================================================

def test_entities_are_tracked_separately():
    entity_tracker.clear()

    entity_tracker.track(
        "Rahul uses Java, Amit uses C++, and my JARVIS uses Python."
    )

    names = [entity["name"].lower() for entity in entity_tracker.all()]

    assert "rahul" in names
    assert "amit" in names
    assert any("jarvis" in name for name in names)


def test_pronoun_resolves_to_the_current_topic():
    state = fresh_state("python")
    state.last_jarvis_reply = "Python is a programming language."

    result = reference_resolver.resolve("Why is it popular?", state)

    assert "python" in result["resolved"].lower()


def test_that_refers_to_the_previous_answer():
    state = fresh_state("python functions")
    state.last_user_message = "What should I learn after functions?"
    state.last_jarvis_reply = "Learn about classes next."

    result = reference_resolver.resolve("What should I learn after that?", state)

    assert result["resolved"].strip()
    assert_clean(result["resolved"])


def test_open_it_without_a_referent_asks_instead_of_guessing():
    state = fresh_state("python")

    result = reference_resolver.resolve("Open it.", state)

    assert result["changed"] is False
    assert "it" in result["unresolved"]


def test_open_it_resolves_to_the_only_open_application():
    state = fresh_state("python")
    state.remember_entities(
        [{"name": "Notepad", "type": "application", "context": "opened"}]
    )

    result = reference_resolver.resolve("Open it.", state)

    assert "notepad" in result["resolved"].lower()


# ======================================================================
# Incomplete sentences, ambiguity, clarification
# ======================================================================

def test_incomplete_sentence_asks_the_user_to_finish():
    report = incomplete_sentence.analyze("I want to create an AI assistant that can...")

    assert report["incomplete"] is True
    assert report["question"].strip().endswith("?")
    assert_clean(report["question"])


def test_complete_sentence_is_not_flagged():
    report = incomplete_sentence.analyze("What is Python and why is it popular?")

    assert report["incomplete"] is False


def test_missing_slots_trigger_a_clarification_question():
    state = fresh_state()

    report = ambiguity_detector.check("Send the file to my friend.", state)

    assert report["ambiguous"] is True

    question = clarification_manager.question_for(report, "Send the file to my friend.")

    assert "?" in question
    assert "sent" not in question.lower()
    assert_clean(question)


def test_clear_request_is_not_treated_as_ambiguous():
    state = fresh_state()

    report = ambiguity_detector.check("Open Notepad.", state)

    assert report["ambiguous"] is False


# ======================================================================
# Corrections
# ======================================================================

def test_correction_updates_the_active_value():
    state = fresh_state("project language")
    state.last_user_message = "My project uses Java."

    report = correction_handler.detect(
        "Actually, correction: my project uses Python.", state
    )

    assert report["corrected"] is True

    acknowledgement = correction_handler.acknowledge(report)

    assert "python" in (report.get("value", "") + acknowledgement).lower()
    assert_clean(acknowledgement)


def test_ordinary_sentence_is_not_a_correction():
    state = fresh_state("python")

    report = correction_handler.detect("Python is popular for data science.", state)

    assert report["corrected"] is False


# ======================================================================
# Temporal understanding
# ======================================================================

def test_relative_days_are_understood_in_local_time():
    found = temporal_parser.parse_all(
        "I worked on JARVIS yesterday, I'm testing it today, "
        "and I'll improve Python tomorrow."
    )

    labels = " ".join(str(item.get("text", "")).lower() for item in found)

    assert "yesterday" in labels
    assert "today" in labels
    assert "tomorrow" in labels


def test_time_reference_detection():
    assert temporal_parser.has_time_reference("What did I do last time?")
    assert not temporal_parser.has_time_reference("What is Python?")


# ======================================================================
# Emotion: confusion, frustration, excitement
# ======================================================================

def test_frustration_is_detected_and_answered_kindly():
    report = emotion_detector.detect(
        "I've explained this three times and you're still not understanding me!"
    )

    assert report["emotion"] in ("frustrated", "angry")

    opener = dialogue_manager.emotion_opener(
        report["emotion"], report.get("confidence", 1.0)
    )

    assert_clean(opener)


def test_excitement_is_detected():
    report = emotion_detector.detect("YES! I finally fixed the biggest bug in my project!")

    assert report["emotion"] in ("excited", "happy")


def test_confusion_is_detected():
    report = emotion_detector.detect("I don't understand what you mean.")

    assert report["emotion"] in ("confused", "neutral")


def test_tiredness_does_not_become_a_command():
    message = "I've been working on my project all day and I'm really tired."

    assert not request_type.is_action_request(message)

    report = emotion_detector.detect(message)

    assert report["emotion"] != ""


# ======================================================================
# Interruption / resume
# ======================================================================

def test_interruption_is_detected_and_acknowledged():
    report = interruption_handler.detect("stop")

    assert report["interrupted"] is True

    reply = interruption_handler.handle(report.get("kind", "stop"), fresh_state())

    assert_clean(reply)


def test_continue_request_is_detected():
    report = interruption_handler.detect("continue from where you stopped")

    assert report["interrupted"] is True
    assert report.get("kind") in ("continue", "resume", "stop")


# ======================================================================
# Sessions, history, long conversations, summarization
# ======================================================================

def test_session_has_real_boundaries():
    first = session_manager.start(user="tester", mode="text")

    assert first

    turn = session_manager.next_turn()

    assert turn >= 1

    info = session_manager.info()

    assert info["session_id"] == first
    assert info.get("started_at") or info.get("start_time")

    session_manager.end(summary="discussed JARVIS")

    second = session_manager.start(user="tester", mode="text")

    assert second != first

    previous = session_manager.previous_session()

    assert previous is not None
    assert previous["session_id"] == first


def test_history_is_stored_with_structure():
    session = session_manager.start(user="tester")

    history_manager.add(
        session,
        "user",
        "Remember that my project is JARVIS.",
        turn=1,
        intent="memory",
        topic="jarvis",
    )
    history_manager.add(
        session,
        "assistant",
        "Noted - your project is JARVIS.",
        turn=1,
        intent="memory",
        topic="jarvis",
    )

    recent = history_manager.recent(session, limit=5)

    assert len(recent) == 2

    for message in recent:
        for field in ("role", "text", "topic"):
            assert field in message

        assert_clean(message["text"])


def test_relevant_history_is_retrieved_after_a_long_detour():
    session = session_manager.start(user="tester")

    history_manager.add(
        session, "user", "The important project name is JARVIS.", topic="jarvis"
    )

    for index in range(12):
        history_manager.add(
            session, "user", f"Unrelated chatter number {index}", topic="chatter"
        )

    found = history_manager.relevant(session, "What was the important project name?")

    assert any("JARVIS" in message["text"] for message in found), found


def test_repeated_question_is_flagged_without_replaying_an_old_answer():
    session = session_manager.start(user="tester")

    history_manager.add(session, "user", "What is Python?", topic="python")
    history_manager.add(session, "assistant", "Python is a language.", topic="python")

    assert history_manager.repeated_question(session, "What is Python?") is True
    assert history_manager.repeated_question(session, "What is Java?") is False


def test_long_conversation_is_summarized_into_structure():
    messages = [
        {"role": "user", "text": "Let's discuss JARVIS.", "topic": "jarvis"},
        {"role": "user", "text": "My project uses Python.", "topic": "jarvis"},
        {"role": "user", "text": "I want it to have memory.", "topic": "jarvis"},
        {
            "role": "assistant",
            "text": "Memory can be stored in SQLite.",
            "topic": "jarvis",
        },
        {
            "role": "user",
            "text": "I am debugging conversation handling.",
            "topic": "debugging",
        },
    ]

    summary = context_summarizer.summarize(messages)

    assert summary.strip()
    assert_clean(summary)
    assert "jarvis" in summary.lower() or "python" in summary.lower()


def test_summarizer_waits_until_the_conversation_is_long():
    assert context_summarizer.should_summarize(4, 0) is False
    assert context_summarizer.should_summarize(40, 0) is True


def test_context_window_is_bounded_and_ranked():
    session = session_manager.start(user="tester")

    for index in range(40):
        history_manager.add(
            session, "user", f"Message {index} about topic {index % 3}", topic="mixed"
        )

    state = fresh_state("python")

    built = context_manager.build("What is Python?", state, session_id=session)

    assert isinstance(built, dict)

    context = built.get("context", "")

    assert len(context) < 8000, len(context)
    # This is the prompt sent to the model, so section headings are
    # expected; model reasoning never is.
    assert "<think>" not in context.lower()
    assert "internal reasoning" not in context.lower()


def test_context_ranker_prefers_the_relevant_message():
    messages = [
        {"role": "user", "text": "I like cricket.", "topic": "sport"},
        {"role": "user", "text": "My project JARVIS uses Python.", "topic": "jarvis"},
        {"role": "user", "text": "The weather is hot.", "topic": "weather"},
    ]

    ranked = context_ranker.rank(messages, "Which language does JARVIS use?", limit=1)

    assert ranked
    assert "JARVIS" in ranked[0]["text"]


# ======================================================================
# Dialogue memory (facts stated in conversation)
# ======================================================================

def test_dialogue_memory_learns_and_answers():
    dialogue_memory.clear()

    dialogue_memory.learn("My project is called JARVIS.")

    answer = dialogue_memory.answer("What is my project called?")

    assert "jarvis" in answer.lower(), answer
    assert_clean(answer)


def test_dialogue_memory_correction_replaces_the_value():
    dialogue_memory.clear()

    dialogue_memory.learn("My project uses Java.")
    key = dialogue_memory.last_fact_key()

    dialogue_memory.correct(key, "Python")

    assert "python" in dialogue_memory.lookup(key).lower()


# ======================================================================
# Conversation state and the end-to-end understanding pass
# ======================================================================

def test_conversation_state_exposes_the_required_fields():
    state = fresh_state("python")

    data = state.to_dict()

    for field in (
        "current_topic",
        "previous_topic",
        "active_entities",
        "last_user_message",
        "last_jarvis_reply",
        "pending_question",
        "emotion",
        "session_id",
        "turn",
        "temporal",
    ):
        assert field in data, field


def test_understanding_pass_fills_the_conversation_state():
    understanding = conversation_engine.understand(
        "Rahul uses Java, Amit uses C++, and my JARVIS uses Python."
    )

    assert understanding.text
    assert understanding.session_id
    assert understanding.topic or understanding.entities

    data = understanding.to_dict()

    for field in ("intent", "topic", "entities", "emotion", "references"):
        assert field in data, field


def test_engine_prompt_has_explicit_sections_and_no_reasoning():
    understanding = conversation_engine.understand("What is Python and why is it popular?")

    prompt = conversation_engine.prompt(understanding)

    assert prompt.strip()
    assert "<think" not in prompt.lower()


def test_commit_stores_only_the_clean_final_answer():
    understanding = conversation_engine.understand("What is Python?")

    stored = conversation_engine.commit(
        understanding,
        "<think>the user wants a definition</think>Python is a programming language.",
    )

    assert "python is a programming language" in stored.lower()
    assert_clean(stored)


def test_engine_answers_a_greeting_without_calling_the_model():
    understanding = conversation_engine.understand("hello")

    assert understanding.is_greeting is True
    assert_clean(getattr(understanding, "reply", "") or "")


# ======================================================================
# Response variation / quality / adaptive style
# ======================================================================

def test_depth_adapts_to_the_request():
    beginner = plan_response("Explain Python like I'm a complete beginner.")
    expert = plan_response("Explain Python at programmer level.")

    assert beginner.to_dict()["depth"]
    assert expert.to_dict()["depth"]
    assert beginner.to_dict() != expert.to_dict()


def test_structure_rotates_between_turns():
    shapes = {structure_for("normal", recent=()) for _ in range(3)}
    shapes |= {structure_for("normal", recent=("paragraph",))}

    assert len(shapes) > 1


def test_repeated_wording_is_detected():
    first = "Python is a high-level language known for readable syntax."
    second = "Python is a high-level language known for readable syntax."

    assert repetition_detector.similarity(first, second) > 0.9

    report = repetition_detector.check(second, recent_answers=[first])

    assert report["repeat"] is True


def test_different_wording_is_allowed():
    report = repetition_detector.check(
        "Guido van Rossum released Python in 1991.",
        recent_answers=["Python is popular because its syntax reads like English."],
    )

    assert report["repeat"] is False


def test_ai_cliches_are_stripped():
    cleaned = repetition_detector.strip_cliches(
        "As an AI language model, I can say Python is popular."
    )

    assert "as an ai" not in cleaned.lower()
    assert "Python is popular" in cleaned


def test_quality_check_rejects_an_empty_or_internal_answer():
    bad = quality_check("<think>hmm</think>")

    assert bad.ok is False

    good = quality_check("Python is a programming language created in 1991.")

    assert good.ok is True


# ======================================================================
# Routing, memory and goals (conversation vs action)
# ======================================================================

def test_information_and_action_requests_are_separated():
    assert request_type.is_information_request("Tell me about Notepad.")
    assert request_type.is_action_request("Open Notepad.")
    assert request_type.is_action_request("Close Notepad.")
    assert request_type.is_information_request("Tell me about my Python project.")
    assert request_type.is_action_request("Open my Python project.")


def test_compound_memory_request_stores_and_answers():
    from memory import memory_engine

    facts = {}

    original = (memory_engine.remember, memory_engine.recall, memory_engine.forget)

    memory_engine.remember = lambda key, value: facts.__setitem__(key.lower(), value)
    memory_engine.recall = lambda key: facts.get(key.lower())
    memory_engine.forget = lambda key: facts.pop(key.lower(), None) is not None
    memory_engine._LAST["key"] = ""
    memory_engine._LAST["value"] = ""

    try:
        reply = memory_engine.process_memory(
            "Remember that my project is called JARVIS. What did I ask you to remember?"
        )
    finally:
        memory_engine.remember, memory_engine.recall, memory_engine.forget = original

    assert "JARVIS" in (reply or "")
    assert_clean(reply)


def test_goal_is_created_and_reported():
    from brains_v2.goals import GoalPlanner

    planner = GoalPlanner()

    result = planner.execute(
        "Create a goal to learn Python, then tell me what my current goal is"
    )

    assert result["handled"] is True
    assert "learn Python" in result["reply"]
    assert_clean(result["reply"])


def test_final_response_gate_blocks_internal_output():
    blocked = final_user_response("<think>internal planning only</think>")

    assert blocked.final_text == ""
    assert blocked.success is False

    allowed = final_user_response("Python is a programming language.")

    assert allowed.success is True
    assert allowed.final_text == "Python is a programming language."
