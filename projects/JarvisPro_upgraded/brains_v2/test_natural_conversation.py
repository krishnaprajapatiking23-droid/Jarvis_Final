from brains_v2.agents.conversation_agent import ConversationAgent


def test_conversation_agent_has_natural_conversation_plan():
    agent = ConversationAgent()

    plan = agent.plan("Tell me about your day")

    assert "Understand user" in plan
    assert "Generate natural reply" in plan
    assert "Maintain conversation" in plan


def test_conversation_agent_handles_normal_conversation():
    agent = ConversationAgent()

    result = agent.execute("What are you doing today?")

    assert result["agent"] == "Conversation Agent"
    assert "reply" in result
    assert result["success"] is True


def test_conversation_agent_handles_follow_up_style_message():
    agent = ConversationAgent()

    result = agent.execute("That's interesting, tell me more")

    assert result["agent"] == "Conversation Agent"
    assert result["success"] is True
    assert isinstance(result["reply"], str)
    assert len(result["reply"].strip()) > 0