"""Wikipedia lookup skill.

Uses the public REST summary endpoint. Offline or blocked networks produce a
clear message instead of a fabricated answer.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional

__all__ = ["WikipediaSkill", "wikipedia_skill", "process_wikipedia"]

API = "https://en.wikipedia.org/api/rest_v1/page/summary/"
TIMEOUT = 8.0
USER_AGENT = "JarvisPro/1.0 (local assistant)"

_TRIGGER = re.compile(
    r"^(?:please\s+)?(?:who\s+is|who\s+was|what\s+is|what\s+are|what\s+was|"
    r"tell\s+me\s+about|look\s+up|wikipedia)\s+(?P<topic>.+)$",
    re.IGNORECASE,
)


class WikipediaSkill:
    name = "wikipedia"
    description = "One-paragraph factual summaries from Wikipedia."

    def can_handle(self, command: Any) -> bool:
        return bool(_TRIGGER.match(str(command or "").strip()))

    def topic(self, command: Any) -> str:
        match = _TRIGGER.match(str(command or "").strip())
        if not match:
            return ""
        return match.group("topic").strip(" ?.!")

    def execute(self, command: Any) -> Dict[str, Any]:
        topic = self.topic(command)
        if not topic:
            return {"success": False, "reply": "What should I look up?"}

        url = API + urllib.parse.quote(topic.replace(" ", "_"))
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})

        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            if error.code == 404:
                return {"success": False,
                        "reply": "Wikipedia has no article called %r." % topic}
            return {"success": False,
                    "reply": "Wikipedia returned an error (%s)." % error.code}
        except (urllib.error.URLError, OSError, ValueError) as error:
            return {"success": False,
                    "reply": "I couldn't reach Wikipedia (%s)."
                             % type(error).__name__}

        extract = payload.get("extract") or ""
        if not extract:
            return {"success": False,
                    "reply": "I found the page but it had no summary."}

        return {
            "success": True,
            "title": payload.get("title", topic),
            "url": (payload.get("content_urls", {})
                    .get("desktop", {}).get("page", "")),
            "reply": extract.strip(),
        }


wikipedia_skill = WikipediaSkill()


def process_wikipedia(command: Any) -> Optional[str]:
    if not wikipedia_skill.can_handle(command):
        return None
    return wikipedia_skill.execute(command).get("reply")
