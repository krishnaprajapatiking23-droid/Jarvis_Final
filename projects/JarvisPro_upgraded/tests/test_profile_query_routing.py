"""Section 8 - preference questions must reach the profile subsystem.

Before this, "What do you know about my preferences?" scored as a knowledge
question and was answered by the model. These tests pin the routing and the
formatting so it cannot regress into ordinary conversation again.
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brains_v2 import core_bridge
from brains_v2.core_bridge import _PROFILE_QUERY, handle_profile
from jarvis_core.profile_store import ProfileStore


class _FakeKernel:
    def __init__(self, store):
        self.profile = store


def _with_store(monkey_store):
    """Point core_bridge.kernel() at a throwaway profile store."""
    original = core_bridge.kernel
    core_bridge.kernel = lambda: _FakeKernel(monkey_store)
    return original


def _restore(original):
    core_bridge.kernel = original


def _store():
    return ProfileStore(db_path=os.path.join(tempfile.mkdtemp(), "profile.db"))


# ------------------------------------------------------------- matching
def test_preference_questions_match():
    for text in (
        "What do you know about my preferences?",
        "what do you know about me",
        "Show my preferences.",
        "list my preferences",
        "tell me my profile",
        "What are my preferences?",
    ):
        assert _PROFILE_QUERY.match(text), text


def test_unrelated_commands_do_not_match():
    for text in (
        "open chrome",
        "what is the capital of France",
        "remind me tomorrow at 7pm",
        "show my running tasks",
        "create a task to study",
    ):
        assert not _PROFILE_QUERY.match(text), text


def test_handler_returns_none_for_unrelated_command():
    assert handle_profile("open chrome") is None
    assert handle_profile("") is None
    assert handle_profile(None) is None


# ------------------------------------------------------------- answering
def test_empty_profile_says_so_without_inventing():
    store = _store()
    original = _with_store(store)
    try:
        reply = handle_profile("What do you know about my preferences?")["reply"]
    finally:
        _restore(original)
    assert "don't have anything recorded" in reply


def test_stored_attributes_are_listed():
    store = _store()
    store.set("favorite_editor", "VS Code")
    store.set("timezone", "Asia/Kolkata")
    original = _with_store(store)
    try:
        reply = handle_profile("What do you know about my preferences?")["reply"]
    finally:
        _restore(original)
    assert "favorite editor: VS Code" in reply
    assert "timezone: Asia/Kolkata" in reply
    assert "2 items" in reply


def test_temporary_preferences_are_labelled():
    store = _store()
    store.set_temporary("focus_mode", "on", ttl_seconds=3600)
    original = _with_store(store)
    try:
        reply = handle_profile("show my preferences")["reply"]
    finally:
        _restore(original)
    assert "temporary" in reply


def test_low_confidence_is_flagged_not_hidden():
    store = _store()
    store.set("guessed_language", "Gujarati", confidence=0.4, source="inference")
    original = _with_store(store)
    try:
        reply = handle_profile("what do you know about me")["reply"]
    finally:
        _restore(original)
    assert "low confidence" in reply


def test_expired_preference_is_not_reported():
    import time

    store = _store()
    store.set("editor", "VS Code")
    store.set_temporary("gone", "x", ttl_seconds=1)
    time.sleep(1.2)
    original = _with_store(store)
    try:
        reply = handle_profile("show my preferences")["reply"]
    finally:
        _restore(original)
    assert "gone" not in reply
    assert "1 item" in reply


def test_unavailable_kernel_is_reported_honestly():
    original = core_bridge.kernel
    core_bridge.kernel = lambda: None
    try:
        reply = handle_profile("show my preferences")["reply"]
    finally:
        core_bridge.kernel = original
    assert "unavailable" in reply.lower()
