"""Reminder pipeline stage.

BUG FIX (two defects):

* The final line of the old ``process()`` was an unconditional
  ``return "Please include a reminder time."``. Any command containing the
  substring "remind" that did not match one of its literal prefixes got that
  sentence -- including ``"show my reminders"``.
* Because this stage runs *before* ``reminder_controller`` in
  ``brains_v2/manager.py`` and always returned a truthy string, the
  controller -- which had proper intent detection -- was unreachable dead
  code for every reminder command.

This module now shares one detector with the controller
(:mod:`brains_v2.intents.reminder_intent`) and returns ``None`` whenever the
command is not actually a reminder operation, so the rest of the pipeline
still gets a chance.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from brains_v2.intents.reminder_intent import detect
from brains_v2.reminders.reminders import add, mutate, show

__all__ = ["process"]


def _reply(text: str) -> Dict[str, str]:
    return {"reply": text}


def process(command: Any) -> Optional[Dict[str, str]]:
    """Handle a reminder command, or return ``None`` to pass it on."""
    intent = detect(command)

    if not intent:
        return None

    kind = intent["type"]

    if kind == "show_reminders":
        return _reply(show())

    if kind == "add_reminder":
        if not intent.get("has_time"):
            return _reply(
                "When should I remind you to %s? Say something like "
                '"in 20 minutes" or "tomorrow at 9".' % intent["title"]
            )
        return _reply(add(intent["title"], intent["time"]))

    if kind in ("cancel", "complete"):
        done = mutate(intent["token"], kind)
        word = "cancelled" if kind == "cancel" else "completed"
        return _reply("Reminder %s." % word if done else "Reminder not found.")

    if kind == "update":
        done = mutate(
            intent["token"], "update", intent.get("title"), intent.get("when")
        )
        return _reply("Reminder updated." if done else "Reminder not found.")

    if kind == "snooze":
        done = mutate(intent["token"], "update", None, intent.get("when"))
        return _reply("Reminder snoozed." if done else "Reminder not found.")

    return None
