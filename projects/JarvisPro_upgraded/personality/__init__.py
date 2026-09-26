"""
Personality System — Adaptive personality, mood, and communication style.

Manages: personality modes, emotional context, greeting styles, conversation modes.
"""

from .emotion import get_emotion, set_emotion
from .greetings import GREETINGS, GREETINGS_NAMED, random_greeting
from .modes import personality, MODES, LANGUAGES, Personality
from .style import follow_up, FOLLOW_UP
from .memory import personality as personality_memory

__all__ = [
    # emotion
    'get_emotion', 'set_emotion',
    # greetings
    'GREETINGS', 'GREETINGS_NAMED', 'random_greeting',
    # modes
    'personality', 'MODES', 'LANGUAGES', 'Personality',
    # style
    'follow_up', 'FOLLOW_UP',
    # memory
    'personality_memory',
]
