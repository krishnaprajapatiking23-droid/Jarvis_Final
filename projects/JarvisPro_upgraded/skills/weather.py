"""Weather skill.

Honest by design: without a configured provider it says so rather than
inventing a forecast. Set JARVIS_WEATHER_URL to a JSON endpoint that accepts
``?q=<place>`` and the skill will use it.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional

__all__ = ["WeatherSkill", "weather_skill", "process_weather"]

_QUESTION = re.compile(
    r"\b(weather|temperature|forecast|how\s+(?:hot|cold|warm)\s+is\s+it|"
    r"is\s+it\s+(?:raining|snowing|sunny))\b",
    re.IGNORECASE,
)
_PLACE = re.compile(r"\b(?:in|at|for)\s+(?P<place>[A-Za-z][A-Za-z\s,.'-]{1,48})$",
                    re.IGNORECASE)
TIMEOUT = 6.0


class WeatherSkill:
    name = "weather"
    description = "Current conditions from a configured weather provider."

    def __init__(self, endpoint: Optional[str] = None):
        self.endpoint = endpoint or os.environ.get("JARVIS_WEATHER_URL", "")

    def configured(self) -> bool:
        return bool(self.endpoint)

    def can_handle(self, command: Any) -> bool:
        return bool(_QUESTION.search(str(command or "")))

    def place(self, command: Any) -> str:
        match = _PLACE.search(str(command or "").strip(" ?."))
        return match.group("place").strip() if match else ""

    def execute(self, command: Any) -> Dict[str, Any]:
        if not self.configured():
            return {
                "success": False,
                "reply": (
                    "I don't have a weather provider configured, so I won't "
                    "guess. Set JARVIS_WEATHER_URL to a JSON endpoint and I'll "
                    "use it."
                ),
            }

        place = self.place(command) or "here"
        url = "%s?q=%s" % (self.endpoint.rstrip("?&"),
                           urllib.parse.quote(place))

        try:
            with urllib.request.urlopen(url, timeout=TIMEOUT) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, OSError, ValueError) as error:
            return {"success": False,
                    "reply": "I couldn't reach the weather service (%s)."
                             % type(error).__name__}

        summary = (payload.get("summary") or payload.get("description")
                   or payload.get("condition") or "")
        temperature = payload.get("temperature", payload.get("temp"))

        if temperature is None and not summary:
            return {"success": False,
                    "reply": "The weather service returned nothing I could read."}

        parts = []
        if summary:
            parts.append(str(summary))
        if temperature is not None:
            parts.append("%s degrees" % temperature)

        return {"success": True, "data": payload,
                "reply": "%s: %s." % (place, ", ".join(parts))}


weather_skill = WeatherSkill()


def process_weather(command: Any) -> Optional[str]:
    if not weather_skill.can_handle(command):
        return None
    return weather_skill.execute(command).get("reply")
