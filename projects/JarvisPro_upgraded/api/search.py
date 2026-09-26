"""Search API facade.

Local workspace search always works. Web search is used only when a provider
is configured, and says so plainly when it is not -- it never invents results.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List

from tools.search import search_tool

__all__ = ["search_local", "search_web", "configured"]

ENDPOINT_ENV = "JARVIS_SEARCH_URL"
TIMEOUT = 8.0


def configured() -> bool:
    return bool(os.environ.get(ENDPOINT_ENV))


def search_local(query: str, path: str = ".") -> Dict[str, Any]:
    return search_tool.execute(query, path)


def search_web(query: str, limit: int = 5) -> Dict[str, Any]:
    endpoint = os.environ.get(ENDPOINT_ENV, "")

    if not endpoint:
        return {
            "success": False,
            "results": [],
            "error": ("no web search provider configured; set %s to a JSON "
                      "endpoint that accepts ?q=" % ENDPOINT_ENV),
        }

    url = "%s?q=%s" % (endpoint.rstrip("?&"), urllib.parse.quote(str(query)))

    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError) as error:
        return {"success": False, "results": [],
                "error": "%s: %s" % (type(error).__name__, error)}

    raw = payload.get("results", payload if isinstance(payload, list) else [])
    results: List[Dict[str, str]] = []
    for item in raw[:limit]:
        if not isinstance(item, dict):
            continue
        results.append({
            "title": str(item.get("title", "")),
            "url": str(item.get("url", item.get("link", ""))),
            "snippet": str(item.get("snippet", item.get("description", ""))),
        })

    return {"success": True, "query": query, "results": results}
