from conversation.identity import identity

SYSTEM_PROMPT = """

You are Jarvis.

You are private.

You are honest.

Never invent facts.

Be concise.

Always help your owner build projects.

"""


def _conversation_context():
    """Ranked context for the current turn, when the engine has one."""

    try:

        from conversation.conversation_engine import conversation_engine

        return conversation_engine.current_context()

    except Exception:

        return ""


def build(command, history=None, context=""):
    """Build the prompt for the local model.

    When the Conversation System has context for this turn (state, topic,
    entities, relevant memory, summary and ranked recent messages) that
    structured context replaces the raw history dump.
    """

    prompt = SYSTEM_PROMPT

    owner = identity.owner()

    if owner:

        prompt += f"\nYou are speaking with {owner}.\n"

    if not context:

        context = _conversation_context()

    if context:

        prompt += "\n" + context.strip() + "\n"

        # The ranked context normally ends with [CURRENT MESSAGE]; append
        # the raw command only when it is missing, so the model always
        # sees what was just asked.
        if command and command.strip() not in context:

            prompt += "\nUser: " + command + "\n"

        return prompt

    if history:

        prompt += "\nPrevious conversation:\n"

        for message in history:

            role = message.get("role", "user")

            text = message.get("text", "")

            prompt += f"{role}: {text}\n"

    prompt += "\nUser: " + command

    return prompt