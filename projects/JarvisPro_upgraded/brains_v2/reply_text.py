"""
==========================================
JARVIS PRO
Reply extraction - one shape for the speaking layer
==========================================

ROOT CAUSE OF ``KeyError: 'reply'``
-----------------------------------
The voice pipeline did ``self._say(reply["reply"])``.  Most routes do
return a ``reply`` key, but several return their payload under a
different name (``{"type": "power", "result": ...}``,
``{"type": "automation", "result": {"status": ..., "app": ...}}``), and
one crash in the speaking layer killed the whole session:

    File "brains_v2/voice/pipeline.py", line 107, in run
        self._say(reply["reply"])
    KeyError: 'reply'

Every caller that turns a brain result into spoken text now goes through
``reply_text()``, so a missing key degrades into an honest sentence
instead of a traceback, and the text is passed through the single
FINAL_USER_RESPONSE gate on the way out.
"""

import logging

from conversation.output_sanitizer import final_user_response

log = logging.getLogger("jarvis.reply_text")

# Checked in order - the first non-empty one wins.
TEXT_KEYS = ("reply", "text", "message", "answer", "result", "output")

FALLBACK = "I don't have a reply for that, and I won't invent one."


def _from_status(payload):
    """Sentence for a structured automation result."""

    status = str(payload.get("status") or "").upper()
    app = str(payload.get("app") or "the application").capitalize()

    if not status:
        return ""

    if status == "OPENED":
        return f"Opening {app}."

    if status == "ALREADY_OPEN":
        return f"{app} is already open."

    if status == "CLOSED":
        return f"Closed {app}."

    if status == "NOT_OPEN":
        return f"{app} wasn't running, so there was nothing to close."

    if status == "FAILED":
        return f"I couldn't do that with {app}, and I won't pretend I did."

    return ""


def reply_text(result, fallback: str = FALLBACK) -> str:
    """The sentence the user may hear for any brain/router result."""

    if result is None:
        return fallback

    value = ""

    if isinstance(result, str):
        value = result

    elif isinstance(result, dict):

        value = _from_status(result)

        if not value:

            for key in TEXT_KEYS:
                candidate = result.get(key)

                if isinstance(candidate, dict):
                    candidate = reply_text(candidate, "")

                elif isinstance(candidate, (int, float)):
                    candidate = str(candidate)

                if isinstance(candidate, str) and candidate.strip():
                    value = candidate
                    break

        if not value:
            log.warning(
                "result had no speakable text (keys=%s)",
                sorted(result.keys()),
            )

    else:
        value = str(result)

    outcome = final_user_response(value)

    return outcome.final_text or fallback


__all__ = ["reply_text", "TEXT_KEYS", "FALLBACK"]
