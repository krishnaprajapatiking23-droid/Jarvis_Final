"""
==========================================
JARVIS PRO
Personality & language modes
==========================================

Roadmap section 6: friendly, professional, developer, serious, teacher,
coach, concise and detailed modes, plus Hindi, Hinglish and English
language modes.

A mode is just a system-prompt fragment plus a few output rules, so it works
with any model and costs nothing.

    from personality.modes import personality

    personality.set_mode("teacher")
    personality.set_language("hinglish")
    prompt = personality.system_prompt()

The chosen mode is saved through the central config, so it survives restarts.
"""

from __future__ import annotations

import threading
from typing import Any


MODES: dict[str, dict[str, str]] = {
    "friendly": {
        "label": "Friendly",
        "prompt": (
            "Be warm, relaxed and encouraging. Speak like a trusted friend. "
            "Light humour is welcome, but never at the owner's expense."
        ),
    },
    "professional": {
        "label": "Professional",
        "prompt": (
            "Be polite, precise and businesslike. No slang, no jokes. "
            "Lead with the answer, then the detail that matters."
        ),
    },
    "developer": {
        "label": "Developer",
        "prompt": (
            "Talk like a senior engineer pairing with the owner. Use exact "
            "technical terms, mention file names and commands, show code when "
            "it helps, and state trade-offs honestly."
        ),
    },
    "serious": {
        "label": "Serious",
        "prompt": (
            "Be direct and focused. No filler, no pleasantries, no humour. "
            "Report facts and next actions only."
        ),
    },
    "teacher": {
        "label": "Teacher",
        "prompt": (
            "Explain so a beginner understands. Define terms, build up step "
            "by step, use one concrete example, and check understanding at "
            "the end with a short question."
        ),
    },
    "coach": {
        "label": "Coach",
        "prompt": (
            "Push the owner towards action. Be motivating but honest, call "
            "out avoidance, and always end with the single next step to take."
        ),
    },
    "concise": {
        "label": "Concise",
        "prompt": (
            "Answer in as few words as possible - ideally one or two "
            "sentences. No preamble, no summary, no repetition."
        ),
    },
    "detailed": {
        "label": "Detailed",
        "prompt": (
            "Give the complete picture: reasoning, alternatives, caveats and "
            "consequences. Structure it so it stays readable."
        ),
    },
}


LANGUAGES: dict[str, dict[str, str]] = {
    "en": {
        "label": "English",
        "prompt": "Reply in clear English.",
    },
    "hi": {
        "label": "Hindi",
        "prompt": (
            "Reply in Hindi using Devanagari script. Keep technical terms in "
            "English where that is what the owner actually says."
        ),
    },
    "hinglish": {
        "label": "Hinglish",
        "prompt": (
            "Reply in Hinglish: Hindi sentence structure written in Roman "
            "script, mixed naturally with English words, the way the owner "
            "speaks. Do not use Devanagari script."
        ),
    },
}


# Modes that change length behaviour rather than tone.
LENGTH_HINTS = {
    "concise": "Keep the whole reply under 40 words.",
    "detailed": "Use as much space as the topic genuinely needs.",
}


class Personality:
    """Current tone and language, plus the prompt they produce."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._mode = "friendly"
        self._language = "en"

        self._load()

    # ---------------------------------------------------- persistence

    def _load(self) -> None:
        try:
            from config import config

            mode = str(config.get("personality.mode", "friendly")).lower()
            language = str(config.get("assistant.language", "en")).lower()

            if mode in MODES:
                self._mode = mode

            if language in LANGUAGES:
                self._language = language

        except Exception:
            pass

    def _persist(self) -> None:
        try:
            from config import config

            config.set("personality.mode", self._mode)
            config.set("assistant.language", self._language)

        except Exception:
            pass

    # ---------------------------------------------------- setting

    def set_mode(self, mode: str) -> dict[str, Any]:
        wanted = str(mode or "").strip().lower()

        if wanted not in MODES:
            return {
                "ok": False,
                "error": f"I do not have a '{mode}' mode.",
                "available": sorted(MODES),
            }

        with self._lock:
            self._mode = wanted
            self._persist()

        return {
            "ok": True,
            "mode": wanted,
            "message": f"Switched to {MODES[wanted]['label']} mode.",
        }

    def set_language(self, language: str) -> dict[str, Any]:
        wanted = str(language or "").strip().lower()
        aliases = {
            "english": "en",
            "hindi": "hi",
            "hinglish": "hinglish",
            "eng": "en",
        }
        wanted = aliases.get(wanted, wanted)

        if wanted not in LANGUAGES:
            return {
                "ok": False,
                "error": f"I cannot speak '{language}' yet.",
                "available": sorted(LANGUAGES),
            }

        with self._lock:
            self._language = wanted
            self._persist()

        return {
            "ok": True,
            "language": wanted,
            "message": f"Switched to {LANGUAGES[wanted]['label']}.",
        }

    # ---------------------------------------------------- reading

    @property
    def mode(self) -> str:
        with self._lock:
            return self._mode

    @property
    def language(self) -> str:
        with self._lock:
            return self._language

    def modes(self) -> list[dict[str, str]]:
        return [
            {"name": name, "label": data["label"]}
            for name, data in sorted(MODES.items())
        ]

    def languages(self) -> list[dict[str, str]]:
        return [
            {"name": name, "label": data["label"]}
            for name, data in sorted(LANGUAGES.items())
        ]

    def system_prompt(self, extra: str = "") -> str:
        """The instruction block to prepend to any model call."""

        with self._lock:
            mode = self._mode
            language = self._language

        try:
            from config import config

            name = str(config.get("assistant.name", "Jarvis"))
            owner = str(config.get("assistant.owner", ""))

        except Exception:
            name, owner = "Jarvis", ""

        lines = [f"You are {name}, a personal desktop assistant."]

        if owner:
            lines.append(f"You are speaking to {owner}, your owner.")

        lines.append(MODES[mode]["prompt"])
        lines.append(LANGUAGES[language]["prompt"])

        hint = LENGTH_HINTS.get(mode)

        if hint:
            lines.append(hint)

        if extra.strip():
            lines.append(extra.strip())

        return "\n".join(lines)

    def detect_request(self, text: str) -> dict[str, Any]:
        """Spot 'talk like a teacher' / 'hindi me bolo' style commands."""

        lowered = str(text or "").lower()
        result: dict[str, Any] = {"mode": "", "language": ""}

        for name in MODES:
            if name in lowered:
                result["mode"] = name
                break

        for word, code in (
            ("hinglish", "hinglish"),
            ("hindi", "hi"),
            ("english", "en"),
        ):
            if word in lowered:
                result["language"] = code
                break

        return result

    def apply_request(self, text: str) -> dict[str, Any]:
        """Detect and apply a mode/language switch in one call."""

        wanted = self.detect_request(text)
        changed: list[str] = []

        if wanted["mode"]:
            outcome = self.set_mode(wanted["mode"])

            if outcome["ok"]:
                changed.append(MODES[wanted["mode"]]["label"] + " mode")

        if wanted["language"]:
            outcome = self.set_language(wanted["language"])

            if outcome["ok"]:
                changed.append(LANGUAGES[wanted["language"]]["label"])

        if not changed:
            return {"ok": False, "changed": [], "message": ""}

        return {
            "ok": True,
            "changed": changed,
            "message": "Switched to " + " and ".join(changed) + ".",
        }

    def status(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "mode_label": MODES[self.mode]["label"],
            "language": self.language,
            "language_label": LANGUAGES[self.language]["label"],
            "modes_available": sorted(MODES),
            "languages_available": sorted(LANGUAGES),
        }


personality = Personality()
