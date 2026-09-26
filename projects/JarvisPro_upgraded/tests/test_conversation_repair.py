"""Regression tests for the conversation-system bug repair.

One test per reported bug class, written so they run offline (no Ollama,
no pytest plugins, no Windows automation).
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from conversation import request_splitter
from conversation.ambiguity_detector import ambiguity_detector, missing_slots
from conversation.clarification_manager import clarification_manager
from conversation.conversation_state import ConversationState
from conversation.reference_resolver import reference_resolver
from conversation import response_quality


def stub_optional_modules():
    """Let automation modules import on machines without pyautogui."""

    import types

    for name in ("pyautogui", "pyperclip", "psutil", "pygetwindow"):
        if name in sys.modules:
            continue
        try:
            __import__(name)
        except Exception:
            module = types.ModuleType(name)
            module.__getattr__ = lambda attribute: (lambda *a, **k: None)
            sys.modules[name] = module


stub_optional_modules()


def source(relative):
    with open(os.path.join(ROOT, relative), "r", encoding="utf-8") as handle:
        return handle.read()


# ======================================================================
# Bug #2 - memory command parsing
# ======================================================================

def test_splitter_separates_memory_instruction_from_question():
    request = request_splitter.split(
        "Remember that my project is called JARVIS. What is my project called?"
    )

    assert request.memory == ["my project is called JARVIS"]
    assert request.questions == ["What is my project called?"]
    assert request.facts() == [("project", "JARVIS")]


def test_splitter_keeps_the_question_out_of_the_stored_fact():
    request = request_splitter.split(
        "Remember this important fact: my project is called JARVIS. "
        "What important fact did I tell you at the beginning?"
    )

    assert request.has_memory
    assert "what important fact" not in request.memory[0].lower()
    assert request.facts() == [("project", "JARVIS")]


def test_history_question_is_not_a_memory_command():
    from brains_v2.intents import memory_intent

    result = memory_intent.detect(
        "My favorite language is Python. What did I just tell you?"
    )

    assert result is None


def test_plain_preference_statement_is_still_stored():
    from brains_v2.intents import memory_intent

    result = memory_intent.detect("My favorite language is Python.")

    assert result is not None
    assert result["type"] == "preference"


def test_memory_intent_returns_the_question_separately():
    from brains_v2.intents import memory_intent

    result = memory_intent.detect(
        "Remember that my project is called JARVIS. What is my project called?"
    )

    assert result["type"] == "remember_fact"
    assert result["text"] == "my project is called JARVIS"
    assert result["question"] == "What is my project called?"


def test_memory_engine_stores_only_the_fact_and_answers_the_question():
    from memory import memory_engine

    store = {}

    original_remember = memory_engine.remember
    original_recall = memory_engine.recall

    memory_engine.remember = lambda key, value: store.__setitem__(key.lower(), value)
    memory_engine.recall = lambda key: store.get(key.lower())

    try:
        reply = memory_engine.process_memory(
            "Remember that my project is called JARVIS. What is my project called?"
        )
    finally:
        memory_engine.remember = original_remember
        memory_engine.recall = original_recall

    assert store == {"project": "JARVIS"}
    assert "JARVIS" in reply
    assert "what is my project called" not in reply.lower()


def test_memory_engine_has_no_hard_coded_owner_name():
    text = source("memory/memory_engine.py")

    assert 'f"Okay Krishna' not in text
    assert "identity.owner()" in text


# ======================================================================
# Bug #12 - incomplete sentences are never stored
# ======================================================================

def test_incomplete_sentence_is_not_stored_as_memory():
    from brains_v2.intents import memory_intent

    request = request_splitter.split("I want to create a system that can...")

    assert request.incomplete
    assert memory_intent.detect("I want to create a system that can...") is None


# ======================================================================
# Bug #3 - planner interface
# ======================================================================

def test_planner_exposes_execute_and_declines_questions():
    from brains_v2.goals import GoalPlanner

    planner = GoalPlanner()

    assert hasattr(planner, "execute")
    assert planner.can_handle("Make a plan for building an AI assistant")
    assert not planner.can_handle("What is the main goal we discussed?")
    assert not planner.can_handle("How to learn Python?")

    plan = planner.execute("Make a plan for building the JARVIS assistant")

    assert plan["handled"] is True
    assert plan["tasks"]

    declined = planner.execute("Tell me about Python.")

    assert declined["handled"] is False


def test_router_no_longer_prints_planner_errors_to_the_user():
    text = source("brains_v2/router_v2.py")

    assert 'print("Planner Error:' not in text
    assert "planner failed on" in text


# ======================================================================
# Bugs #4 / #5 - conversation must not reach app automation
# ======================================================================

def test_app_matching_requires_a_real_application():
    from automation.apps import match_app

    assert match_app("open notepad") == "notepad"
    assert match_app("open chrome for me") == "chrome"
    assert match_app("Open it.") is None
    assert match_app("open python") is None
    assert (
        match_app("I've explained this three times and you're still not understanding me!")
        is None
    )


def test_app_module_has_no_debug_printing():
    text = source("automation/apps.py")

    code = [line for line in text.splitlines() if "print(" in line]

    assert code == []


def test_router_guards_the_automation_route():
    text = source("brains_v2/router_v2.py")

    assert "target = match_app(command)" in text


def test_manager_requires_a_target_before_deciding_open():
    text = source("brains_v2/manager.py")

    assert "match_app(command)" in text
    assert "is_action_request(command)" in text


# ======================================================================
# Bug #4 - reference resolution never invents a target
# ======================================================================

def test_open_it_without_a_referent_stays_unresolved():
    state = ConversationState()
    state.current_topic = "python"

    result = reference_resolver.resolve("Open it.", state)

    assert result["changed"] is False
    assert "python" not in result["resolved"].lower()
    assert "it" in result["unresolved"]


def test_determiner_this_is_not_treated_as_a_reference():
    state = ConversationState()
    state.current_topic = "file operations"

    result = reference_resolver.resolve(
        "I've explained this three times and you're still not understanding me!",
        state,
    )

    assert result["resolved"].lower().startswith("i've explained this three times")


def test_relative_that_is_not_substituted():
    state = ConversationState()
    state.current_topic = "python"

    result = reference_resolver.resolve(
        "I want to create a system that can automate my work", state
    )

    assert "system that can" in result["resolved"]


# ======================================================================
# Bug #6 - missing parameters require clarification
# ======================================================================

def test_send_without_file_or_recipient_is_flagged():
    assert missing_slots("send the file to my friend", "send") == [
        "file",
        "recipient",
    ]

    report = ambiguity_detector.check("Send the file to my friend.", ConversationState())

    assert report["ambiguous"] is True
    assert report["reason"] == "missing_parameters"


def test_clarification_question_names_the_missing_parameters():
    report = ambiguity_detector.check("Send the file to my friend.", ConversationState())
    question = clarification_manager.question_for(report, "Send the file to my friend.")

    assert "which file" in question.lower()
    assert "to whom" in question.lower()


def test_a_named_file_and_recipient_needs_no_clarification():
    assert missing_slots("send report.pdf to Rahul", "send") == []


# ======================================================================
# Bugs #1 / #13 - honest LLM failure reporting
# ======================================================================

def test_provider_reports_distinct_failure_reasons():
    from brains_v2.llm.ollama_provider import MIN_ANSWER_TOKENS, STATUS_MESSAGES

    for key in (
        "offline",
        "model_missing",
        "timeout",
        "transport",
        "malformed",
        "empty",
        "error",
    ):
        assert key in STATUS_MESSAGES

    assert len(set(STATUS_MESSAGES.values())) == len(STATUS_MESSAGES)
    assert MIN_ANSWER_TOKENS >= 256


def test_status_messages_are_never_decorated_or_retried():
    from brains_v2.llm.ollama_provider import STATUS_MESSAGES

    for message in STATUS_MESSAGES.values():
        report = response_quality.check(message)

        assert report.unavailable is True, message


def test_old_ollama_sentence_is_gone_from_the_provider():
    text = source("brains_v2/llm/ollama_provider.py")

    # The old sentinel must not be returned anywhere any more (it may still
    # be mentioned in the module docstring that documents the root cause).
    assert 'return "Empty response received from Ollama."' not in text
    assert "STATUS_MESSAGES" in text
