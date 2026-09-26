"""Ollama API facade.

Never imports ``ollama`` at module level -- that unguarded import in eight
other modules used to break whole import chains on machines without the
package. Everything here degrades to a clear error instead.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from compat.ollama_safe import OllamaUnavailable, available, ollama

__all__ = ["available", "chat", "models", "health"]

DEFAULT_MODEL = "qwen3:4b"


def chat(prompt: str, model: str = DEFAULT_MODEL,
         system: Optional[str] = None) -> Dict[str, Any]:
    if not available():
        return {"success": False,
                "error": "the ollama package is not installed", "reply": ""}

    messages: List[Dict[str, str]] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": str(prompt)})

    try:
        response = ollama.chat(model=model, messages=messages)
    except OllamaUnavailable as error:
        return {"success": False, "error": str(error), "reply": ""}
    except Exception as error:
        return {"success": False,
                "error": "%s: %s" % (type(error).__name__, error), "reply": ""}

    content = ""
    if isinstance(response, dict):
        content = str(response.get("message", {}).get("content", ""))

    return {"success": bool(content), "reply": content, "model": model}


def models() -> List[str]:
    if not available():
        return []
    try:
        listing = ollama.list()
    except Exception:
        return []
    entries = listing.get("models", []) if isinstance(listing, dict) else []
    return [str(entry.get("name", "")) for entry in entries if entry.get("name")]


def health() -> Dict[str, Any]:
    return {"available": available(), "models": models()}
