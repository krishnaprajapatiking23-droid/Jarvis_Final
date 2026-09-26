"""
Humanizer

This module used to wrap every reply in a randomly chosen opener and
closer ("Alright, ... Let me know if you need anything else."), which is
exactly what made JARVIS sound like a template.

It now does the opposite job: it *cleans* the model's text - stripping
reasoning traces and stock assistant phrases - and leaves the wording to
the response variation layer, where it is driven by conversation context
and generation parameters instead of ``random.choice``.

The public name ``humanize`` is unchanged so existing callers keep
working.
"""

from conversation.repetition_detector import strip_cliches


def polish(text):
    """Tidy a model reply without adding canned wording."""

    if not text:

        return ""

    return strip_cliches(str(text))


def humanize(text):
    """Backwards-compatible alias for :func:`polish`."""

    return polish(text)


__all__ = ["polish", "humanize"]
