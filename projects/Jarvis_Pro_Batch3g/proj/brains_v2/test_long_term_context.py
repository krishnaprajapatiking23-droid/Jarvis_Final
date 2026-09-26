from brains_v2.conversation import Conversation
from brains_v2.semantic.database import memory
from brains_v2.semantic.manager import remember, recall


def test_long_term_context_can_store_conversation_fact():
    test_memory = "TEST_USER_PREFERS_PYTHON_FOR_JARVIS"

    remember(test_memory)

    results = recall("PYTHON JARVIS")

    assert test_memory in results


def test_long_term_context_persists_outside_conversation():
    conversation = Conversation()

    conversation.add(
        "I want to build Jarvis with Python",
        "Python is a good choice for Jarvis."
    )

    remember("The user wants to build Jarvis with Python.")

    conversation = Conversation()

    results = recall("user Jarvis Python")

    assert any("Jarvis" in item and "Python" in item for item in results)