"""Read and summarise a web page.

Uses BeautifulSoup when installed and a conservative HTML stripper otherwise.
Refuses non-http schemes and local addresses so a command cannot be used to
probe the machine's own network.
"""

from __future__ import annotations

import html
import ipaddress
import re
import socket
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict

__all__ = ["read_page", "extract_text"]

TIMEOUT = 12.0
MAX_BYTES = 2 * 1024 * 1024
USER_AGENT = "JarvisPro/1.0 (local assistant)"

_SCRIPT = re.compile(r"<(script|style|noscript)[^>]*>.*?</\1>",
                     re.IGNORECASE | re.DOTALL)
_TAG = re.compile(r"<[^>]+>")
_WHITESPACE = re.compile(r"\s+")
_TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)


def _is_private(hostname: str) -> bool:
    try:
        address = ipaddress.ip_address(socket.gethostbyname(hostname))
    except (OSError, ValueError):
        return True
    return (address.is_private or address.is_loopback or address.is_reserved
            or address.is_link_local)


def extract_text(markup: str) -> str:
    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(markup, "html.parser")
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        return _WHITESPACE.sub(" ", soup.get_text(" ")).strip()
    except Exception:
        pass

    stripped = _SCRIPT.sub(" ", markup)
    stripped = _TAG.sub(" ", stripped)
    return _WHITESPACE.sub(" ", html.unescape(stripped)).strip()


def read_page(url: str, limit: int = 4000) -> Dict[str, Any]:
    parsed = urllib.parse.urlparse(str(url or ""))

    if parsed.scheme not in ("http", "https"):
        return {"success": False, "error": "only http and https URLs are allowed"}

    if not parsed.hostname or _is_private(parsed.hostname):
        return {"success": False,
                "error": "refusing to fetch a local or private address"}

    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})

    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            raw = response.read(MAX_BYTES)
            charset = response.headers.get_content_charset() or "utf-8"
    except (urllib.error.URLError, OSError, ValueError) as error:
        return {"success": False,
                "error": "%s: %s" % (type(error).__name__, error)}

    markup = raw.decode(charset, errors="replace")
    title_match = _TITLE.search(markup)
    text = extract_text(markup)

    return {
        "success": True,
        "url": url,
        "title": (html.unescape(title_match.group(1)).strip()
                  if title_match else ""),
        "text": text[:limit],
        "truncated": len(text) > limit,
        "characters": len(text),
    }
