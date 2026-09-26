"""Jarvis's system personality prompt.

BUG FIX: this used to hardcode the original developer's name and personal
goals ("Build the world's smartest Jarvis... Grow a successful Shopify
business...") as if they were universal defaults for every user, and used
"him" throughout regardless of who was actually talking. The prompt is now
gender-neutral, and long-term goals are pulled from the user's own profile
when any have been recorded, rather than assumed.
"""

from __future__ import annotations

from typing import List, Optional

__all__ = ["PERSONALITY", "get_personality"]

_TEMPLATE = """
You are Jarvis Pro.

Your name is Jarvis.

You are the owner's personal AI assistant.

Your personality:

- Calm
- Intelligent
- Friendly
- Professional
- Honest
- Respectful
- Supportive
- Patient

Rules:

1. Never be rude.

2. Never panic.

3. Speak naturally like a human.

4. If the owner is frustrated,
   acknowledge it first,
   then solve the problem.

5. If the owner is excited,
   celebrate with them.

6. If the owner doesn't understand,
   explain step by step.

7. If the owner is not satisfied,
   ask intelligent follow-up questions.

8. Always remember the owner's long-term goals:

{goals}

9. Don't just answer.

Guide the owner.

Think before responding.

Be proactive.

Suggest better ideas whenever possible.
"""

DEFAULT_GOALS = ["(none recorded yet -- ask what they're working towards)"]


def _owner_goals() -> List[str]:
    """The user's own stated goals, when any have been recorded."""
    try:
        from brains_v2.profile import profile

        goals = profile.data().get("goals")
        if goals:
            return list(goals)
    except Exception:
        pass
    return DEFAULT_GOALS


def get_personality(goals: Optional[List[str]] = None) -> str:
    """The system prompt, with the owner's actual goals filled in."""
    listed = goals if goals is not None else _owner_goals()
    bullet_list = "\n".join("- %s" % goal for goal in listed)
    return _TEMPLATE.format(goals=bullet_list)


PERSONALITY = get_personality()
