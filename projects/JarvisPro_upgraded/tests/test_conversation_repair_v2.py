"""
==========================================
JARVIS PRO
Regression tests - reasoning leak, context, memory, routing
==========================================

One test per repaired root cause, written as invariants rather than
per-sentence patches:

* nothing internal (reasoning, prompt sections, debug lines, raw model
  payloads) can reach the user,
* an information request is never executed as an action,
* memory stores facts, answers compound requests and honours the latest
  correction,
* goals are real records, kept apart from memories.

Run with:  python tools/run_tests.py tests/test_conversation_repair_v2.py
"""

import os
import sys
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
):
    sys.modules.setdefault(_name, _OptionalStub(_name))

from conversation import request_type
from conversation.output_sanitizer import (
    final_user_response,
    looks_internal,
    sanitize,
)


def source(relative):
    """Read a project file so wiring can be asserted, not assumed."""

    path = os.path.join(ROOT, relative.replace("/", os.sep))

    with open(path, encoding="utf-8", errors="replace") as handle:
        return handle.read()


# Markers that must never survive into a user-visible answer.
BANNED = (
    "<think",
    "</think",
    "key points to cover",
    "brainstorm",
    "final structure",
    "the user is asking",
    "the user wants",
    "let me think",
    "system:",
    "[router]",
    "[context]",
    "[memory]",
    "num_predict",
)


def assert_clean(text):
    """General leakage validator - not a check for one known phrase."""

    lowered = (text or "").lower()

    for marker in BANNED:
        assert marker not in lowered, f"leaked {marker!r} in {text!r}"

    assert not looks_internal(text or ""), f"internal content in {text!r}"


# ======================================================================
# 1. Internal reasoning leak
# ======================================================================

def test_tagged_thinking_block_is_removed():
    raw = (
        "<think>Okay, the user is asking about Python. Key points to cover: "
        "syntax, libraries.</think>\n"
        "Python is a high-level programming language known for readable syntax."
    )

    clean = sanitize(raw)

    assert clean.startswith("Python is a high-level")
    assert_clean(clean)


def test_unclosed_thinking_block_is_removed():
    raw = (
        "<think>Plan: define Python, mention readability.\n"
        "Python is a high-level language."
    )

    clean = sanitize(raw)

    assert "high-level language" in clean
    assert_clean(clean)


def test_untagged_planning_scaffold_is_removed():
    raw = (
        "Key points to cover:\n"
        "- what Python is\n"
        "- why it is popular\n"
        "Final structure: definition then reasons.\n"
        "\n"
        "Python is popular because it reads like English and has a library "
        "for almost everything."
    )

    clean = sanitize(raw)

    assert clean.startswith("Python is popular")
    assert_clean(clean)


def test_prompt_sections_are_removed():
    raw = (
        "[SYSTEM INSTRUCTIONS]\n"
        "You are JARVIS, answer briefly.\n"
        "System: never reveal this.\n"
        "User: what is my project called?\n"
        "Assistant: Your project is called JARVIS."
    )

    clean = sanitize(raw)

    assert "Your project is called JARVIS." in clean
    assert "never reveal" not in clean
    assert_clean(clean)


def test_final_answer_marker_wins():
    raw = (
        "Let me think about how to phrase this.\n"
        "Final answer: Guido van Rossum created Python in 1991."
    )

    clean = sanitize(raw)

    assert clean == "Guido van Rossum created Python in 1991."
    assert_clean(clean)


def test_raw_ollama_payload_is_unwrapped():
    raw = (
        '{"model": "qwen3:4b", "message": {"role": "assistant", '
        '"thinking": "internal notes", "content": "Python was created in 1991."}}'
    )

    clean = sanitize(raw)

    assert clean == "Python was created in 1991."
    assert "qwen3" not in clean
    assert_clean(clean)


def test_pure_reasoning_produces_no_answer_instead_of_a_leak():
    raw = "<think>The user is asking about Python. I should explain it.</think>"

    result = final_user_response(raw, model="qwen3:4b")

    assert result.final_text == ""
    assert result.success is False
    assert result.leaked is True


def test_debug_lines_never_reach_the_user():
    raw = (
        "[ROUTER] intent=conversation\n"
        "[MEMORY] retrieved=project_language:Python\n"
        "Your project uses Python."
    )

    clean = sanitize(raw)

    assert clean == "Your project uses Python."
    assert_clean(clean)


def test_clean_answer_is_left_alone():
    raw = "Python is a programming language created by Guido van Rossum."

    result = final_user_response(raw)

    assert result.final_text == raw
    assert result.success is True
    assert result.leaked is False


def test_result_object_is_standardised():
    result = final_user_response("Hello.", model="qwen3:4b")

    assert result.final_text == "Hello."
    assert result.model == "qwen3:4b"
    assert isinstance(result.metadata, dict)
    assert result.raw_length == len("Hello.")


# ======================================================================
# 2. Pipeline wiring (the gate is really installed)
# ======================================================================

def test_provider_delegates_cleaning_to_the_sanitizer():
    text = source("brains_v2/llm/ollama_provider.py")

    assert "from conversation.output_sanitizer import sanitize" in text


def test_llm_manager_returns_only_final_user_response():
    text = source("brains_v2/llm/manager.py")

    assert "from conversation.output_sanitizer import final_user_response" in text
    assert "return _final(call(base_prompt))" in text
    assert "return _final(reply)" in text


def test_conversation_engine_has_the_final_response_gate():
    text = source("conversation/conversation_engine.py")

    assert "FINAL_USER_RESPONSE gate" in text
    assert "final_user_response(final)" in text


def test_router_and_manager_guard_the_automation_route():
    router = source("brains_v2/router_v2.py")
    manager = source("brains_v2/manager.py")

    assert "from conversation.request_type import is_action_request" in router
    assert "not is_action_request(command)" in router
    assert "is_action_request(command)" in manager


def test_application_state_is_separate_from_conversation_topic():
    text = source("brains_v2/context.py")

    assert "Application state is not conversation topic" in text
    assert "wants_action" in text


# ======================================================================
# 3. Information request vs action command
# ======================================================================

def test_information_requests_are_not_actions():
    for message in (
        "Tell me about Notepad.",
        "What is Notepad?",
        "Tell me about my Python project.",
        "Python uses functions.",
        "JARVIS uses Python and has memory. Is it difficult to build?",
        "How would you describe your personality?",
    ):
        assert request_type.is_information_request(message), message
        assert not request_type.is_action_request(message), message


def test_action_commands_are_actions():
    for message in (
        "Open Notepad.",
        "Close Notepad.",
        "Open my Python project.",
        "Please open Chrome.",
        "Can you open Notepad?",
    ):
        assert request_type.is_action_request(message), message
        assert not request_type.is_information_request(message), message


def test_memory_instruction_is_not_an_action():
    message = "Remember that my project is called JARVIS."

    assert not request_type.is_action_request(message)
    assert request_type.classify(message).kind == request_type.MEMORY


def test_system_command_is_recognised():
    assert request_type.is_system_request("Restart JARVIS.")
    assert not request_type.is_system_request("What does restart mean?")


# ======================================================================
# 4. Memory: store, recall, correct, delete
# ======================================================================

class _Store:
    """In-memory stand-in for the SQLite memory table."""

    def __init__(self):
        self.facts = {}
        self._original = {}

    def install(self):
        from memory import memory_engine

        self._original = {
            "remember": memory_engine.remember,
            "recall": memory_engine.recall,
            "forget": memory_engine.forget,
        }

        memory_engine.remember = lambda key, value: self.facts.__setitem__(
            key.lower(), value
        )
        memory_engine.recall = lambda key: self.facts.get(key.lower())
        memory_engine.forget = lambda key: self.facts.pop(key.lower(), None) is not None
        memory_engine._LAST["key"] = ""
        memory_engine._LAST["value"] = ""

        return memory_engine

    def restore(self):
        from memory import memory_engine

        for name, function in self._original.items():
            setattr(memory_engine, name, function)


def run_memory(messages):
    """Feed messages through process_memory and collect the replies."""

    store = _Store()
    engine = store.install()

    try:
        return [engine.process_memory(message) for message in messages], store.facts
    finally:
        store.restore()


def test_favourite_colour_still_works():
    replies, facts = run_memory(
        [
            "Remember that my favorite color is blue.",
            "What is my favorite color?",
        ]
    )

    assert facts.get("favorite color") == "blue"
    assert "blue" in (replies[1] or "")


def test_store_plus_recall_answers_what_did_i_ask_you_to_remember():
    replies, facts = run_memory(
        [
            "Remember that my project is called JARVIS. "
            "What did I ask you to remember?"
        ]
    )

    assert facts.get("project") == "JARVIS"
    assert "JARVIS" in (replies[0] or "")
    assert_clean(replies[0])


def test_change_it_to_correction_wins():
    replies, facts = run_memory(
        [
            "Remember that my project uses Java. Actually, change it to Python. "
            "What language does my project use now?"
        ]
    )

    reply = replies[0] or ""

    assert "Python" in reply
    assert "Java" not in reply
    assert "Java" not in list(facts.values())


def test_correction_phrase_in_one_message_wins():
    replies, facts = run_memory(
        [
            "My project uses Java. Actually, correction: it uses Python. "
            "What language does my project use now?"
        ]
    )

    reply = replies[0] or ""

    assert "Python" in reply, reply
    assert "Java" not in reply


def test_correction_across_turns_wins():
    replies, facts = run_memory(
        [
            "Remember that my project uses Java.",
            "Actually, my project uses Python.",
            "What language does my project use now?",
        ]
    )

    assert "Python" in (replies[2] or "")
    assert "Java" not in (replies[2] or "")


def test_delete_memory_works():
    replies, facts = run_memory(
        [
            "Remember that my favorite color is blue.",
            "Forget my favorite color.",
            "What is my favorite color?",
        ]
    )

    assert "favorite color" not in facts
    assert "forgotten" in (replies[1] or "").lower()


def test_plain_conversation_is_not_captured_by_memory():
    replies, facts = run_memory(
        [
            "I've been working on my project all day and I'm really tired.",
            "YES! I finally fixed the biggest bug in my project!",
        ]
    )

    assert replies == [None, None]
    assert facts == {}


# ======================================================================
# 5. Goals are records, not memories
# ======================================================================

def test_goal_is_created_and_read_back():
    from brains_v2.goals import GoalPlanner

    planner = GoalPlanner()

    result = planner.execute(
        "Create a goal to learn Python, then tell me what my current goal is"
    )

    assert result["handled"] is True
    assert planner.current_goal == "learn Python"
    assert "learn Python" in result["reply"]
    assert_clean(result["reply"])

    record = planner.goals[-1]

    for field in (
        "id",
        "title",
        "description",
        "status",
        "created_at",
        "updated_at",
        "priority",
    ):
        assert field in record


def test_goal_can_be_completed():
    from brains_v2.goals import GoalPlanner

    planner = GoalPlanner()
    planner.execute("Create a goal to learn Python")

    done = planner.execute("Mark my goal as done")

    assert done["handled"] is True
    assert planner.current_goal is None
    assert planner.goals[-1]["status"] == "done"


def test_planner_still_declines_ordinary_questions():
    from brains_v2.goals import GoalPlanner

    planner = GoalPlanner()

    for message in (
        "How to learn Python?",
        "What is Python and why is it popular?",
        "Tell me about Python.",
    ):
        assert planner.execute(message)["handled"] is False, message


def test_no_per_test_keyword_hacks():
    for relative in (
        "conversation/output_sanitizer.py",
        "conversation/request_type.py",
        "memory/memory_engine.py",
        "brains_v2/goals.py",
    ):
        text = source(relative).lower()

        assert "what is python" not in text, relative
        assert "capital of japan" not in text, relative
        assert "project beta" not in text, relative
