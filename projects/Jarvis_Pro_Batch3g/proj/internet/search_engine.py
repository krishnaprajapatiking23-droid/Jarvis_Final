"""
==========================================
JARVIS PRO
Research / web search engine
==========================================

Roadmap section 14 (Research manager) and 22 (Knowledge acquisition).

Modes:

    search    general web lookup
    news      recent news on a topic
    research  multi-query deep dive, then a model-written summary
    price     shopping / price lookup
    compare   side-by-side comparison of two things

Everything is free and keyless:

  * DuckDuckGo HTML endpoint is parsed directly (no API key, no scraping
    library needed - ``beautifulsoup4`` is used when available and a plain
    regex fallback when not);
  * summaries are produced by the local model through ``core.model_router``.

When the machine is offline, every call returns a clean
``{"ok": False, "message": ...}`` instead of raising.
"""

from __future__ import annotations

import html
import json
import re
import threading
import time
import urllib.parse
from typing import Any

from config import config
from core.observability import observability


USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

DDG_HTML = "https://html.duckduckgo.com/html/?q="
DDG_ANSWER = "https://api.duckduckgo.com/?format=json&no_html=1&q="

CACHE_TTL = 900.0


class SearchEngine:

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._cache: dict[str, tuple[float, Any]] = {}

    # ---------------------------------------------------- http

    def _fetch(self, url: str, timeout: float = 15.0) -> str:
        import urllib.request

        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})

        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read().decode("utf-8", "ignore")

    def online(self) -> bool:
        try:
            self._fetch("https://duckduckgo.com/", timeout=5.0)

            return True

        except Exception:
            return False

    # ---------------------------------------------------- parsing

    def _parse_with_soup(self, page: str, limit: int) -> list[dict[str, str]]:
        try:
            from bs4 import BeautifulSoup

        except Exception:
            return []

        results: list[dict[str, str]] = []

        soup = BeautifulSoup(page, "html.parser")

        for node in soup.select(".result")[: limit * 2]:
            link = node.select_one("a.result__a")

            if link is None:
                continue

            snippet = node.select_one(".result__snippet")

            results.append(
                {
                    "title": link.get_text(" ", strip=True),
                    "url": self._clean_url(str(link.get("href", ""))),
                    "snippet": snippet.get_text(" ", strip=True) if snippet else "",
                }
            )

            if len(results) >= limit:
                break

        return results

    def _parse_with_regex(self, page: str, limit: int) -> list[dict[str, str]]:
        pattern = re.compile(
            r'result__a[^>]*href="(?P<url>[^"]+)"[^>]*>(?P<title>.*?)</a>',
            re.DOTALL,
        )
        snippet_pattern = re.compile(
            r'result__snippet[^>]*>(?P<text>.*?)</a>',
            re.DOTALL,
        )

        snippets = [
            self._strip(match.group("text"))
            for match in snippet_pattern.finditer(page)
        ]

        results: list[dict[str, str]] = []

        for index, match in enumerate(pattern.finditer(page)):
            results.append(
                {
                    "title": self._strip(match.group("title")),
                    "url": self._clean_url(match.group("url")),
                    "snippet": snippets[index] if index < len(snippets) else "",
                }
            )

            if len(results) >= limit:
                break

        return results

    def _strip(self, text: str) -> str:
        return html.unescape(re.sub(r"<[^>]+>", "", text)).strip()

    def _clean_url(self, url: str) -> str:
        """DuckDuckGo wraps targets in a redirect - unwrap it."""

        url = html.unescape(url)

        if "uddg=" in url:
            parsed = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
            target = parsed.get("uddg", [""])[0]

            if target:
                return target

        if url.startswith("//"):
            return "https:" + url

        return url

    # ---------------------------------------------------- core search

    def search(self, query: str, limit: int = 6) -> dict[str, Any]:
        """Plain web search with a short in-memory cache."""

        query = str(query or "").strip()

        if not query:
            return {"ok": False, "message": "Tell me what to search for."}

        key = f"search::{query}::{limit}"
        cached = self._cached(key)

        if cached is not None:
            return cached

        started = time.time()

        try:
            page = self._fetch(DDG_HTML + urllib.parse.quote_plus(query))

        except Exception as error:
            observability.warn("search", f"fetch failed: {error}", query=query)

            return {
                "ok": False,
                "message": "I could not reach the internet just now.",
                "error": str(error),
            }

        results = self._parse_with_soup(page, limit) or self._parse_with_regex(
            page, limit
        )

        payload = {
            "ok": bool(results),
            "query": query,
            "count": len(results),
            "results": results,
            "instant_answer": self.instant_answer(query),
            "elapsed": round(time.time() - started, 2),
        }

        if not results:
            payload["message"] = "I did not find anything useful for that."

        observability.record("search.web", time.time() - started, ok=bool(results))

        self._store(key, payload)

        return payload

    def instant_answer(self, query: str) -> str:
        """DuckDuckGo instant answer - good for facts and definitions."""

        try:
            raw = self._fetch(DDG_ANSWER + urllib.parse.quote_plus(query), timeout=10)
            data = json.loads(raw)

        except Exception:
            return ""

        for field in ("AbstractText", "Answer", "Definition"):
            value = str(data.get(field) or "").strip()

            if value:
                return value

        topics = data.get("RelatedTopics") or []

        if topics and isinstance(topics[0], dict):
            return str(topics[0].get("Text") or "").strip()

        return ""

    # ---------------------------------------------------- modes

    def news(self, topic: str, limit: int = 6) -> dict[str, Any]:
        return self.search(f"{topic} latest news", limit)

    def price(self, product: str, limit: int = 6) -> dict[str, Any]:
        return self.search(f"{product} price buy online", limit)

    def compare(self, first: str, second: str) -> dict[str, Any]:
        found = self.search(f"{first} vs {second} comparison", 6)

        if not found.get("ok"):
            return found

        summary = self._summarise(
            f"Compare {first} and {second}",
            found["results"],
            instruction=(
                "Write a short comparison with a clear recommendation. "
                "Use two bullet lists (strengths of each) and one verdict line."
            ),
        )

        return dict(found, mode="compare", summary=summary)

    def research(self, topic: str, depth: int = 3) -> dict[str, Any]:
        """Multi-query deep dive followed by a written summary."""

        topic = str(topic or "").strip()

        if not topic:
            return {"ok": False, "message": "Tell me what to research."}

        angles = [
            topic,
            f"{topic} explained",
            f"{topic} advantages and disadvantages",
            f"{topic} latest developments",
        ][: max(depth, 1)]

        collected: list[dict[str, str]] = []
        seen: set[str] = set()

        for angle in angles:
            found = self.search(angle, 5)

            for item in found.get("results", []):
                if item["url"] in seen:
                    continue

                seen.add(item["url"])
                collected.append(item)

        if not collected:
            return {
                "ok": False,
                "message": "I could not gather sources for that topic.",
            }

        summary = self._summarise(
            topic,
            collected,
            instruction=(
                "Write a structured research briefing: a two-line overview, "
                "4-6 key findings as bullets, and a closing takeaway. "
                "Only use the supplied sources."
            ),
        )

        return {
            "ok": True,
            "mode": "research",
            "topic": topic,
            "queries": angles,
            "sources": collected[:15],
            "count": len(collected),
            "summary": summary,
        }

    def run(self, query: str, mode: str = "search") -> dict[str, Any]:
        """Single entry point used by the tool registry."""

        mode = str(mode or "search").strip().lower()

        if mode == "news":
            return self.news(query)

        if mode == "price":
            return self.price(query)

        if mode == "research":
            return self.research(query)

        if mode == "compare":
            parts = re.split(r"\s+vs\.?\s+|\s+versus\s+", query, maxsplit=1)

            if len(parts) == 2:
                return self.compare(parts[0].strip(), parts[1].strip())

            return self.search(query)

        return self.search(query)

    # ---------------------------------------------------- summarising

    def _summarise(
        self,
        topic: str,
        results: list[dict[str, str]],
        instruction: str,
    ) -> str:
        if not results:
            return ""

        sources = "\n\n".join(
            f"[{index + 1}] {item['title']}\n{item['url']}\n{item['snippet']}"
            for index, item in enumerate(results[:10])
        )

        prompt = (
            f"You are the research module of JARVIS.\n\n"
            f"TOPIC: {topic}\n\n"
            f"SOURCES:\n{sources}\n\n"
            f"TASK: {instruction}\n"
            "Never invent facts that are not in the sources."
        )

        try:
            from core.model_router import router

            return router.text(
                prompt,
                capability="research",
                options={"temperature": 0.3, "num_predict": 900},
            )

        except Exception as error:
            observability.warn("search", f"summary failed: {error}")

            return ""

    # ---------------------------------------------------- cache

    def _cached(self, key: str) -> Any:
        with self._lock:
            entry = self._cache.get(key)

            if entry and time.time() - entry[0] < CACHE_TTL:
                return entry[1]

            self._cache.pop(key, None)

        return None

    def _store(self, key: str, value: Any) -> None:
        with self._lock:
            self._cache[key] = (time.time(), value)

            if len(self._cache) > 100:
                oldest = sorted(self._cache.items(), key=lambda item: item[1][0])

                for stale, _ in oldest[:50]:
                    self._cache.pop(stale, None)

    def clear_cache(self) -> None:
        with self._lock:
            self._cache.clear()


search_engine = SearchEngine()
