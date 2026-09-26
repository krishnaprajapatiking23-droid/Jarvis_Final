"""YouTube skill: opens search results or a channel in the default browser."""

from __future__ import annotations

import re
import urllib.parse
import webbrowser
from typing import Any, Dict, Optional

__all__ = ["YouTubeSkill", "youtube_skill", "process_youtube"]

SEARCH = "https://www.youtube.com/results?search_query="
HOME = "https://www.youtube.com"

_TRIGGER = re.compile(
    r"\b(?:play|search|find|open|watch)\b[^.]*\byoutube\b|"
    r"\byoutube\b[^.]*\b(?:play|search|find|open|watch)\b|"
    r"^\s*youtube\b",
    re.IGNORECASE,
)
_QUERY = re.compile(
    r"(?:play|search(?:\s+for)?|find|watch)\s+(?P<query>.+?)"
    r"(?:\s+on\s+youtube)?\s*$",
    re.IGNORECASE,
)


class YouTubeSkill:
    name = "youtube"
    description = "Opens YouTube search results in the browser."

    def can_handle(self, command: Any) -> bool:
        return bool(_TRIGGER.search(str(command or "")))

    def query(self, command: Any) -> str:
        text = re.sub(r"\byoutube\b", " ", str(command or ""), flags=re.IGNORECASE)
        match = _QUERY.search(text.strip(" ?."))
        if not match:
            return ""
        # "play lofi on youtube" loses "youtube" above, leaving a dangling
        # preposition; drop it so the search query is just "lofi".
        return re.sub(r"\s+(?:on|in|at|for)\s*$", "",
                      match.group("query").strip(), flags=re.IGNORECASE).strip()

    def execute(self, command: Any) -> Dict[str, Any]:
        query = self.query(command)
        url = SEARCH + urllib.parse.quote(query) if query else HOME

        try:
            opened = webbrowser.open(url)
        except Exception as error:
            return {"success": False,
                    "reply": "I couldn't open the browser (%s)."
                             % type(error).__name__}

        if not opened:
            return {"success": False, "url": url,
                    "reply": "No browser is available. The link is: %s" % url}

        return {
            "success": True,
            "url": url,
            "reply": ("Searching YouTube for %s." % query if query
                      else "Opening YouTube."),
        }


youtube_skill = YouTubeSkill()


def process_youtube(command: Any) -> Optional[str]:
    if not youtube_skill.can_handle(command):
        return None
    return youtube_skill.execute(command).get("reply")
