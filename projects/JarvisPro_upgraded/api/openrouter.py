"""OpenRouter API facade (optional cloud model, roadmap section 35).

Disabled unless OPENROUTER_API_KEY is set, so a local-only install never
makes a network call by accident.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

__all__ = ["available", "chat", "health"]

ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "openai/gpt-4o-mini"
TIMEOUT = 30.0


def available() -> bool:
    return bool(os.environ.get("OPENROUTER_API_KEY"))


def chat(prompt: str, model: str = DEFAULT_MODEL,
         system: Optional[str] = None) -> Dict[str, Any]:
    key = os.environ.get("OPENROUTER_API_KEY", "")

    if not key:
        return {"success": False, "reply": "",
                "error": "OPENROUTER_API_KEY is not set; cloud models are off"}

    messages: List[Dict[str, str]] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": str(prompt)})

    body = json.dumps({"model": model, "messages": messages}).encode("utf-8")
    request = urllib.request.Request(
        ENDPOINT, data=body,
        headers={"Authorization": "Bearer %s" % key,
                 "Content-Type": "application/json"})

    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError) as error:
        return {"success": False, "reply": "",
                "error": "%s: %s" % (type(error).__name__, error)}

    choices = payload.get("choices", [])
    content = ""
    if choices:
        content = str(choices[0].get("message", {}).get("content", ""))

    return {"success": bool(content), "reply": content, "model": model}


def health() -> Dict[str, Any]:
    return {"available": available(), "endpoint": ENDPOINT}
