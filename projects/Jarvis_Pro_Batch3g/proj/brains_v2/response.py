"""
==========================================
JARVIS PRO
Action reply builder
==========================================

This module used to pick a random line from a hardcoded template table
and append an automatic follow-up question to every reply, which is one
of the reasons JARVIS sounded like a script.  Command acknowledgements
now come from the response generator, which rotates wording instead of
repeating or randomising it, and no follow-up is bolted on.
"""

from conversation.response_generator import response_generator


def generate(result):
    """Turn a controller result into a short spoken acknowledgement."""

    if result is None:
        # Nothing was executed - usually "Open it." with no
        # referent.  Ask instead of implying something happened.
        return "What would you like me to open?"

    # New architecture: controllers already return a finished sentence.
    if isinstance(result, str):
        return result

    status = str(result.get("status", "opened")).upper()
    app = str(result.get("app", "Application")).capitalize()

    if status == "ALREADY_OPEN":
        return f"{app} is already open."

    if status == "CLOSED":
        return f"Closed {app}."

    if status == "NOT_OPEN":
        return f"{app} wasn't running, so there was nothing to close."

    return response_generator.acknowledge(
        "open",
        app,
        success=status != "FAILED",
    )
