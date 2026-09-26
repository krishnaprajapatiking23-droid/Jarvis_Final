"""
==========================================
JARVIS PRO
Regression tests for the live-session bugs
==========================================

The developer-mode session showed four defects that the offline suites
did not cover:

1. ``KeyError: 'reply'`` killed the session at
   ``brains_v2/voice/pipeline.py`` line 107.
2. The model echoed our prompt back ("We are in the middle of
   conversation about Python (the topic). The user has just asked ...",
   "RESPONSE DIRECTIVES ...") and that scratchpad was spoken as the answer.
3. Memory turns answered with the internal label "Memory request detected."
4. "Close it." was routed to ``open_app``, so JARVIS answered
   "Notepad is already open."
"""

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

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

from automation import apps
from brains_v2 import response as action_response
from brains_v2.reply_text import FALLBACK, reply_text
from conversation.output_sanitizer import (
    final_user_response,
    looks_internal,
    sanitize,
)


# The exact text the user saw in the live session.
LEAK = """We are in the middle of conversation about Python (the topic). The user has just asked "what is python?" after our greeting exchange.

From previous context:
- User: Hello -> Jarvis: Hey. What can I do for you?
Now, the current message from user is: what is python?

RESPONSE DIRECTIVES (for this reply):
1. Give a natural, conversational answer of about three to six sentences.
2. Structure: one-sentence answer first, then explanation, then example.

Previous answer that I gave was:
"We are in the middle of conversation about Python (the topic)."

But note: The system says we have already answered this question before.

Let me reconstruct:"""


# ======================================================================
# 1. the crash
# ======================================================================
def test_a_result_without_a_reply_key_does_not_crash():
    """``{"type": "power", "result": ...}`` used to raise KeyError."""

    spoken = reply_text({"type": "power", "result": "Shutting down now."})

    assert spoken == "Shutting down now."


def test_an_empty_result_falls_back_honestly():
    assert reply_text({"type": "automation"}) == FALLBACK
    assert reply_text(None) == FALLBACK


def test_a_structured_automation_result_becomes_a_sentence():
    spoken = reply_text(
        {"type": "automation", "result": {"status": "CLOSED", "app": "notepad"}}
    )

    assert spoken == "Closed Notepad."


def test_a_plain_string_result_is_passed_through():
    assert reply_text("Opening Calculator.") == "Opening Calculator."


def test_the_speaking_layer_no_longer_indexes_the_reply_key():
    source = (ROOT / "brains_v2" / "voice" / "pipeline.py").read_text(
        encoding="utf-8", errors="ignore"
    )

    assert 'reply["reply"]' not in source
    assert "reply_text(reply)" in source


def test_internal_content_never_survives_reply_extraction():
    assert reply_text({"reply": LEAK}) == FALLBACK


# ======================================================================
# 2. prompt echo
# ======================================================================
def test_prompt_echo_is_recognised_as_internal():
    assert looks_internal(LEAK)


def test_prompt_echo_is_refused_by_the_final_gate():
    result = final_user_response(LEAK)

    assert result.final_text == ""
    assert result.success is False
    assert result.leaked is True


def test_individual_echo_lines_are_internal():
    lines = (
        "We are in a situation where the user asked about Python.",
        "RESPONSE DIRECTIVES (for this reply):",
        "But note: The system says we have already answered this question before.",
        "Let me re-read the instructions carefully.",
        "<i>checks previous interaction patterns</i>",
    )

    for line in lines:
        assert looks_internal(line), line


def test_a_real_answer_is_still_delivered_unchanged():
    answer = (
        "Python is a high-level programming language known for readable "
        "syntax. It is popular because one language covers scripting, web "
        "back ends and machine learning."
    )

    result = final_user_response(answer)

    assert result.success is True
    assert result.final_text == answer
    assert sanitize(answer) == answer


def test_the_provider_refuses_to_hand_back_its_reasoning_tail():
    from brains_v2.llm import ollama_provider

    tail = ollama_provider._answer_from_reasoning(
        "First block of reasoning that is long enough to be kept.\n\n"
        "The user has just asked what Python is, so I should explain it."
    )

    assert tail
    assert ollama_provider._internal(tail)


def test_the_provider_keeps_a_clean_reasoning_tail():
    from brains_v2.llm import ollama_provider

    tail = ollama_provider._answer_from_reasoning(
        "Some planning text.\n\n"
        "Python is a high-level language with a very readable syntax."
    )

    assert tail
    assert not ollama_provider._internal(tail)


# ======================================================================
# 3. memory label
# ======================================================================
def test_the_router_no_longer_answers_with_a_memory_label():
    source = (ROOT / "brains_v2" / "router_v2.py").read_text(
        encoding="utf-8", errors="ignore"
    )

    assert "Memory request detected" not in source
    assert "process_memory" in source


class FakeMemory:
    """In-memory store so the tests never touch the real database."""

    def __enter__(self):
        from memory import memory_engine

        self.engine = memory_engine
        self.facts = {}
        self.original = {
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

    def __exit__(self, *error):
        for name, function in self.original.items():
            setattr(self.engine, name, function)

        return False


def test_the_memory_engine_answers_the_question_in_the_same_message():
    with FakeMemory() as engine:
        answer = engine.process_memory(
            "Remember that JARVIS uses Python. What language does it use?"
        )

    assert answer
    assert "python" in answer.lower()
    assert not looks_internal(answer)


def test_the_latest_correction_wins():
    with FakeMemory() as engine:
        engine.process_memory(
            "Remember that JARVIS uses Python. What language does it use?"
        )

        answer = engine.process_memory(
            "Actually, JARVIS uses Java now. What language does it use?"
        )

    assert answer
    assert "java" in answer.lower()
    assert "python" not in answer.lower()


# ======================================================================
# 4. close means close
# ======================================================================
def test_close_requests_are_detected():
    assert apps.is_close_request("Close notepad.")
    assert apps.is_close_request("close chrome")
    assert apps.is_close_request("quit calculator")


def test_open_requests_are_not_close_requests():
    assert not apps.is_close_request("Open notepad.")
    assert not apps.is_close_request("launch chrome")


def test_close_without_a_named_application_asks_instead_of_acting():
    assert apps.close_app("Close it.") is None


def test_the_router_closes_instead_of_opening():
    source = (ROOT / "brains_v2" / "router_v2.py").read_text(
        encoding="utf-8", errors="ignore"
    )

    assert "is_close_request(command)" in source
    assert "close_app(command)" in source


def test_close_statuses_have_their_own_sentences():
    assert action_response.generate(
        {"status": "CLOSED", "app": "notepad"}
    ) == "Closed Notepad."

    assert "nothing to close" in action_response.generate(
        {"status": "NOT_OPEN", "app": "notepad"}
    )


def test_close_app_is_no_longer_a_stub():
    source = (ROOT / "automation" / "apps.py").read_text(
        encoding="utf-8", errors="ignore"
    )

    assert "close_app is not implemented" not in source
    assert "NOT_OPEN" in source
