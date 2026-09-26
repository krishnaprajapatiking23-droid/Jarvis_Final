"""
==========================================
JARVIS PRO
Tests: greeting / farewell variation
==========================================

Greetings are answered without calling the model (they must be instant
and must never be executed as a command), so they need their own
variation check: saying "hello" a hundred times must not produce
"Good afternoon, Krishna." a hundred times.
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from conversation import store
from conversation.dialogue_manager import dialogue_manager, reset_rotation
from conversation.identity import identity


def _fresh_engine():
    store.use_database(os.path.join(tempfile.mkdtemp(), "greetings.db"))
    store.create_tables()

    from conversation.conversation_engine import ConversationEngine

    reset_rotation()
    return ConversationEngine(mode="text")


# ----------------------------------------------------------------------
def test_greeting_reply_is_never_empty():
    reset_rotation()
    for text in ("hello", "hi", "hey", "hii", "namaste", "good morning"):
        assert dialogue_manager.greeting_reply(text).strip()


def test_hundred_hellos_are_not_the_same_line():
    """The headline requirement: 100 greetings, many different replies."""
    reset_rotation()
    replies = [dialogue_manager.greeting_reply("hello") for _ in range(100)]

    unique = set(replies)
    assert len(unique) >= 20, sorted(unique)

    # No reply may be used for more than a small share of the turns.
    worst = max(replies.count(reply) for reply in unique)
    assert worst <= 12, worst


def test_consecutive_greetings_differ():
    reset_rotation()
    replies = [dialogue_manager.greeting_reply("hello") for _ in range(12)]
    for first, second in zip(replies, replies[1:]):
        assert first != second


def test_owner_name_is_occasional_not_constant():
    reset_rotation()

    # This test needs an owner name to exist at all. core/config.py now ships
    # OWNER_NAME = "" on purpose, so that a fresh install does not greet its
    # new owner by the original developer's name - which is exactly the string
    # this test's docstring was written around. Supply a name for the duration
    # rather than depending on host configuration.
    identity._cache = "Testowner"

    try:
        name = identity.owner()
        replies = [dialogue_manager.greeting_reply("hey") for _ in range(24)]
        with_name = [reply for reply in replies if name and name in reply]

        # Used sometimes...
        assert with_name
        # ...but far from every turn.
        assert len(with_name) <= len(replies) // 2

    finally:
        identity.reset()


def test_explicit_greeting_language_is_mirrored():
    reset_rotation()
    for _ in range(6):
        assert "morning" in dialogue_manager.greeting_reply("good morning").lower()
    reset_rotation()
    for _ in range(6):
        assert "namaste" in dialogue_manager.greeting_reply("namaste").lower()


def test_wellbeing_question_gets_a_status_answer_that_varies():
    reset_rotation()
    replies = [dialogue_manager.greeting_reply("how are you") for _ in range(8)]
    assert len(set(replies)) >= 5, replies


def test_farewells_vary_too():
    reset_rotation()
    replies = [dialogue_manager.farewell_reply("bye") for _ in range(8)]
    assert len(set(replies)) >= 5, replies


def test_engine_greeting_turns_are_varied_end_to_end():
    engine = _fresh_engine()
    replies = []
    for text in ["hello", "hi", "hey", "hii", "hello", "hey", "hiii", "hello"]:
        result = engine.understand(text)
        assert result.is_greeting
        assert result.handled
        replies.append(result.handled_reply)
        engine.commit(result, result.handled_reply)

    assert len(set(replies)) >= 6, replies


def test_greeting_is_still_not_treated_as_a_command():
    engine = _fresh_engine()
    result = engine.understand("hello")
    assert result.intent == "greeting"
    assert result.needs_llm is False


# ----------------------------------------------------------------------
def test_rotation_counters_survive_a_restart():
    """A new process must not start the greeting cycle from zero again.

    Otherwise the first "hello" after every launch is the same line,
    which is exactly what it looked like from the outside.
    """
    import json
    import pathlib

    # ``conversation.dialogue_manager`` is also the name of the shared
    # instance, so reach for the module itself explicitly.
    module = sys.modules["conversation.dialogue_manager"]

    folder = tempfile.mkdtemp()
    state = os.path.join(folder, "dialogue_rotation.json")

    original_file = module._STEP_FILE
    module.reset_rotation(persist=True)
    module._STEP_FILE = pathlib.Path(state)

    try:
        first_run = [module.dialogue_manager.greeting_reply("hello") for _ in range(3)]

        with open(state, "r", encoding="utf-8") as handle:
            assert json.load(handle)["greeting"] == 2

        # Simulate a restart: counters cleared, file still on disk.
        module._STEPS.clear()
        module._STEPS_LOADED = False

        after_restart = module.dialogue_manager.greeting_reply("hello")
        assert after_restart != first_run[0]
    finally:
        module._STEP_FILE = original_file
        module.reset_rotation()
