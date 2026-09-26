"""Prompt template manager (roadmap section 35: Prompt / Template Manager)."""

from __future__ import annotations

import json
import os
import re
import string
from typing import Any, Dict, List, Optional

__all__ = ["PromptManager", "prompt_manager", "render"]

STORE = os.path.join("data", "prompts.json")

BUILT_IN = {
    "chat": "You are Jarvis, a concise personal assistant.\n\nUser: $command",
    "coding": ("You are Jarvis helping with code. Answer with working code and "
               "a one-line explanation.\n\nTask: $command"),
    "research": ("You are Jarvis researching a question. Give the answer, then "
                 "list the sources you used.\n\nQuestion: $command"),
    "summarise": "Summarise the following in at most $sentences sentences:\n\n$text",
    "explain": "Explain $topic to someone with $level experience.",
    "correct": ("The previous attempt failed with: $error\n"
                "Produce a corrected version.\n\nOriginal: $original"),
}


class PromptManager:
    """Named, versioned prompt templates with safe substitution."""

    def __init__(self, path: Optional[str] = None):
        self.path = path or STORE
        self._templates: Dict[str, str] = dict(BUILT_IN)
        self.load()

    def load(self) -> None:
        if not os.path.exists(self.path):
            return
        try:
            with open(self.path, "r", encoding="utf-8") as handle:
                stored = json.load(handle)
            if isinstance(stored, dict):
                self._templates.update(
                    {k: v for k, v in stored.items() if isinstance(v, str)})
        except (OSError, json.JSONDecodeError):
            pass

    def save(self) -> None:
        custom = {k: v for k, v in self._templates.items()
                  if BUILT_IN.get(k) != v}
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as handle:
            json.dump(custom, handle, indent=2)

    def names(self) -> List[str]:
        return sorted(self._templates)

    def get(self, name: str) -> Optional[str]:
        return self._templates.get(name)

    def set(self, name: str, template: str) -> None:
        self._templates[str(name)] = str(template)
        self.save()

    def delete(self, name: str) -> bool:
        if name in BUILT_IN:
            self._templates[name] = BUILT_IN[name]
            self.save()
            return True
        removed = self._templates.pop(name, None) is not None
        if removed:
            self.save()
        return removed

    def placeholders(self, name: str) -> List[str]:
        template = self.get(name) or ""
        return sorted(set(re.findall(r"\$(\w+)", template)))

    def render(self, name: str, **values: Any) -> str:
        """Fill a template. Missing placeholders are left visible, not blank,
        so a broken prompt is obvious rather than silently truncated."""
        template = self.get(name)
        if template is None:
            raise KeyError("no prompt template called %r" % name)
        return string.Template(template).safe_substitute(
            {k: str(v) for k, v in values.items()})


prompt_manager = PromptManager()


def render(name: str, **values: Any) -> str:
    return prompt_manager.render(name, **values)
