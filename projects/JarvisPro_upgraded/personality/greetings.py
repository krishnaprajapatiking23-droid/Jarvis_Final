"""Greeting phrases used when Jarvis first responds in a session.

BUG FIX: this previously hardcoded the original developer's name ("Krishna")
into every greeting, so any other user would be greeted by a stranger's name.
Greetings now accept the current owner's name as a parameter and fall back to
a name-free phrase when none is known, instead of assuming who is talking.
"""

from __future__ import annotations

import random
from typing import Optional

__all__ = ["GREETINGS", "GREETINGS_NAMED", "random_greeting"]

# Used when no owner name is known yet.
GREETINGS = [
    "Hey there!",
    "Welcome back.",
    "Good to see you again!",
    "Hello, what's today's mission?",
    "Hi! Ready to build something amazing?",
]

# {name} is filled in with the current owner's name when one is known.
GREETINGS_NAMED = [
    "Hey {name}!",
    "Welcome back, {name}.",
    "Good to see you again, {name}!",
    "Hello {name}, what's today's mission?",
    "Hi {name}! Ready to build something amazing?",
]


def random_greeting(name: Optional[str] = None) -> str:
    """A random greeting, personalised with ``name`` when one is given."""
    if name:
        return random.choice(GREETINGS_NAMED).format(name=name)
    return random.choice(GREETINGS)
