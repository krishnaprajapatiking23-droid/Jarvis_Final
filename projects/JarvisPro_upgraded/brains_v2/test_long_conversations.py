from brains_v2.conversation import Conversation


def test_long_conversation_preserves_all_messages():
    conversation = Conversation()

    for i in range(100):
        conversation.add(f"user-{i}", f"jarvis-{i}")

    history = conversation.history()

    assert len(history) == 100
    assert history[0]["user"] == "user-0"
    assert history[-1]["user"] == "user-99"


def test_long_conversation_last_message():
    conversation = Conversation()

    for i in range(100):
        conversation.add(f"user-{i}", f"jarvis-{i}")

    assert conversation.last()["user"] == "user-99"
    assert conversation.last()["jarvis"] == "jarvis-99"