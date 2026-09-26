"""
Legacy conversation helpers.

Kept for backwards compatibility with the older command path.  The
context helpers now write to the ``Context`` object exported by
``conversation.context`` (they used to subscript it, which raised
``TypeError`` the first time ``remember()`` was called).

New work should use ``conversation.conversation_engine`` instead.
"""

from conversation.context import CONTEXT
from conversation.followup import follow
from conversation.history import history, MAX_HISTORY
from conversation.personality import follow_up
from conversation.questions import ask


def human_response(answer):
    return f"{answer}\n\n{follow()}"


def human_question(answer):
    return f"{answer}\n\n{ask()}"


def remember(intent, app, action):
    """Record the last intent/app/action on the shared context object."""
    CONTEXT.last_intent = intent
    CONTEXT.last_app = app
    CONTEXT.last_action = action
    CONTEXT.last_command = action or intent
    return CONTEXT


def current():
    """The shared conversation context object."""
    return CONTEXT


def add_history(user, jarvis):
    history.append({
        "user": user,
        "jarvis": jarvis,
    })

    while len(history) > MAX_HISTORY:
        history.pop(0)

    return history


def get_history():
    return history


def continue_conversation(text):
    return f"{text}\n\n{follow_up()}"
