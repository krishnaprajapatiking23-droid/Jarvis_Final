"""Translation skill.

Offline it handles the Hindi/Hinglish/English phrase pairs Jarvis actually
uses; for anything else it says plainly that a translation backend is needed
rather than returning the input unchanged and pretending.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Optional

__all__ = ["TranslatorSkill", "translator_skill", "process_translator"]

# Small built-in phrasebook for the languages this assistant speaks.
PHRASEBOOK = {
    ("en", "hi"): {
        "hello": "namaste",
        "thank you": "dhanyavaad",
        "thanks": "shukriya",
        "good morning": "suprabhat",
        "good night": "shubh ratri",
        "how are you": "aap kaise hain",
        "yes": "haan",
        "no": "nahin",
        "please": "kripya",
        "sorry": "maaf kijiye",
        "what is your name": "aapka naam kya hai",
        "my name is": "mera naam hai",
        "goodbye": "alvida",
        "water": "paani",
        "food": "khana",
        "friend": "dost",
    },
}
PHRASEBOOK[("hi", "en")] = {v: k for k, v in PHRASEBOOK[("en", "hi")].items()}

LANGUAGES = {
    "hindi": "hi", "hinglish": "hi", "english": "en",
    "hi": "hi", "en": "en",
}

_TRIGGER = re.compile(
    r"^(?:please\s+)?translate\s+(?P<text>.+?)\s+(?:in|into|to)\s+"
    r"(?P<language>[a-z]+)\s*$",
    re.IGNORECASE,
)


class TranslatorSkill:
    name = "translator"
    description = "Translates short phrases between English and Hindi."

    def can_handle(self, command: Any) -> bool:
        return bool(_TRIGGER.match(str(command or "").strip()))

    def execute(self, command: Any) -> Dict[str, Any]:
        match = _TRIGGER.match(str(command or "").strip())
        if not match:
            return {"success": False, "reply": "What should I translate?"}

        text = match.group("text").strip(" \"'")
        target = LANGUAGES.get(match.group("language").lower())

        if not target:
            return {"success": False,
                    "reply": "I only translate between English and Hindi."}

        source = "hi" if target == "en" else "en"
        book = PHRASEBOOK.get((source, target), {})
        key = text.lower().strip(" ?.!")

        if key in book:
            return {"success": True, "source": source, "target": target,
                    "reply": book[key]}

        return {
            "success": False,
            "reply": (
                "That phrase isn't in my offline phrasebook. For general "
                "translation I need a translation backend configured."
            ),
        }


translator_skill = TranslatorSkill()


def process_translator(command: Any) -> Optional[str]:
    if not translator_skill.can_handle(command):
        return None
    return translator_skill.execute(command).get("reply")
