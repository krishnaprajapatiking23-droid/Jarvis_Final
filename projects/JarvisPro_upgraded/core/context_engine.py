"""
==========================================
JARVIS PRO
Context engine
==========================================

Roadmap section 2: context assembly, ranking, compression, expiration and
conflict resolution, feeding context-aware decision making.

This does not replace the existing ``context/`` package - it collects from it
(and from memory, profile, system state, time and the active session) and
turns everything into one ranked, size-limited context block that can be put
in front of a model.

    from core.context_engine import context_engine

    context_engine.remember("user_goal", "build the agent loop", weight=0.9)
    block = context_engine.assemble("what was I working on")

Every provider is optional and isolated: if ``context/`` or ``memory/`` is
unavailable, the engine simply returns less context instead of failing.
"""

from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable


# Context types from the roadmap, each with a default weight and lifetime.
KINDS: dict[str, dict[str, float]] = {
    "identity": {"weight": 1.0, "ttl": 0.0},
    "profile": {"weight": 0.9, "ttl": 0.0},
    "goal": {"weight": 0.95, "ttl": 86400.0},
    "task": {"weight": 0.85, "ttl": 7200.0},
    "memory": {"weight": 0.7, "ttl": 0.0},
    "session": {"weight": 0.6, "ttl": 3600.0},
    "screen": {"weight": 0.5, "ttl": 120.0},
    "system": {"weight": 0.45, "ttl": 120.0},
    "time": {"weight": 0.4, "ttl": 60.0},
    "environment": {"weight": 0.35, "ttl": 600.0},
}

DEFAULT_BUDGET = 1800
STOP_WORDS = {
    "the", "a", "an", "is", "was", "are", "were", "my", "me", "i", "you",
    "to", "of", "and", "on", "in", "for", "what", "how", "do", "did", "it",
    "that", "this", "with", "at", "be", "can", "please", "jarvis",
}


@dataclass
class ContextItem:
    key: str
    value: str
    kind: str = "memory"
    weight: float = 0.5
    created: float = field(default_factory=time.time)
    ttl: float = 0.0
    source: str = "runtime"

    @property
    def expired(self) -> bool:
        if self.ttl <= 0:
            return False

        return (time.time() - self.created) > self.ttl

    @property
    def age(self) -> float:
        return time.time() - self.created

    def report(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "value": self.value,
            "kind": self.kind,
            "weight": round(self.weight, 3),
            "age": round(self.age, 1),
            "source": self.source,
            "expired": self.expired,
        }


class ContextEngine:
    """Assembles, ranks, compresses and expires context."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._items: dict[str, ContextItem] = {}
        self._providers: dict[str, Callable[[], dict[str, Any]]] = {}

        self._register_default_providers()

    # ---------------------------------------------------- storing

    def remember(
        self,
        key: str,
        value: Any,
        kind: str = "memory",
        weight: float | None = None,
        ttl: float | None = None,
        source: str = "runtime",
    ) -> ContextItem:
        """Add or replace a context item (conflict resolution: newest wins)."""

        settings = KINDS.get(kind, {"weight": 0.5, "ttl": 0.0})
        item = ContextItem(
            key=str(key),
            value=str(value).strip(),
            kind=kind if kind in KINDS else "memory",
            weight=float(settings["weight"] if weight is None else weight),
            ttl=float(settings["ttl"] if ttl is None else ttl),
            source=source,
        )

        with self._lock:
            self._items[item.key] = item

        return item

    def forget(self, key: str) -> bool:
        with self._lock:
            return self._items.pop(str(key), None) is not None

    def clear(self) -> None:
        with self._lock:
            self._items.clear()

    def expire(self) -> int:
        """Drop expired items (roadmap: context expiration)."""

        with self._lock:
            dead = [key for key, item in self._items.items() if item.expired]

            for key in dead:
                self._items.pop(key, None)

            return len(dead)

    # ---------------------------------------------------- providers

    def register_provider(
        self,
        name: str,
        provider: Callable[[], dict[str, Any]],
    ) -> None:
        """Providers are called on every assemble to collect live context."""

        with self._lock:
            self._providers[str(name)] = provider

    def _register_default_providers(self) -> None:
        self.register_provider("time", self._time_context)
        self.register_provider("identity", self._identity_context)
        self.register_provider("system", self._system_context)
        self.register_provider("screen", self._screen_context)
        self.register_provider("profile", self._profile_context)

    def _time_context(self) -> dict[str, Any]:
        from datetime import datetime

        now = datetime.now()
        hour = now.hour

        if hour < 12:
            part = "morning"

        elif hour < 17:
            part = "afternoon"

        elif hour < 21:
            part = "evening"

        else:
            part = "night"

        return {
            "current_time": {
                "value": now.strftime("%A %d %B %Y, %I:%M %p") + f" ({part})",
                "kind": "time",
            }
        }

    def _identity_context(self) -> dict[str, Any]:
        try:
            from config import config

            return {
                "owner": {
                    "value": str(config.get("assistant.owner", "")),
                    "kind": "identity",
                },
                "assistant": {
                    "value": str(config.get("assistant.name", "Jarvis")),
                    "kind": "identity",
                },
                "language": {
                    "value": str(config.get("assistant.language", "en")),
                    "kind": "identity",
                },
            }

        except Exception:
            return {}

    def _system_context(self) -> dict[str, Any]:
        try:
            from core.system_monitor import monitor

            snapshot = monitor.snapshot()

            if not snapshot.get("available"):
                return {}

            return {
                "system_state": {
                    "value": monitor.report(snapshot),
                    "kind": "system",
                }
            }

        except Exception:
            return {}

    def _screen_context(self) -> dict[str, Any]:
        try:
            from context.manager import get_context

            data = get_context()

        except Exception:
            return {}

        if not isinstance(data, dict):
            return {}

        window = str(data.get("window") or "").strip()
        running = [
            name
            for name, active in data.items()
            if name != "window" and active
        ]

        found: dict[str, Any] = {}

        if window:
            found["active_window"] = {"value": window, "kind": "screen"}

        if running:
            found["running_apps"] = {
                "value": ", ".join(running),
                "kind": "environment",
            }

        return found

    def _profile_context(self) -> dict[str, Any]:
        try:
            from memory.profile import get_profile

            profile = get_profile()

        except Exception:
            return {}

        if not isinstance(profile, dict) or not profile:
            return {}

        parts = [
            f"{key}: {value}"
            for key, value in list(profile.items())[:10]
            if value not in (None, "", [], {})
        ]

        if not parts:
            return {}

        return {"profile": {"value": "; ".join(parts), "kind": "profile"}}

    def collect(self) -> int:
        """Run every provider and store what they return."""

        with self._lock:
            providers = dict(self._providers)

        stored = 0

        for name, provider in providers.items():
            try:
                produced = provider()

            except Exception:
                continue

            if not isinstance(produced, dict):
                continue

            for key, payload in produced.items():
                if isinstance(payload, dict):
                    value = payload.get("value", "")
                    kind = str(payload.get("kind", "memory"))

                else:
                    value, kind = payload, "memory"

                if str(value).strip():
                    self.remember(key, value, kind=kind, source=name)
                    stored += 1

        return stored

    # ---------------------------------------------------- ranking

    def _keywords(self, text: str) -> set[str]:
        words = re.findall(r"[a-z0-9']+", str(text or "").lower())

        return {word for word in words if word not in STOP_WORDS and len(word) > 2}

    def score(self, item: ContextItem, query: str = "") -> float:
        """Relevance = importance + freshness + keyword overlap."""

        score = item.weight

        # freshness: newer context matters more, but never below zero
        if item.ttl > 0:
            remaining = max(0.0, 1.0 - (item.age / item.ttl))
            score += remaining * 0.3

        else:
            score += 0.15

        if query:
            wanted = self._keywords(query)

            if wanted:
                text = self._keywords(f"{item.key} {item.value}")
                overlap = len(wanted & text)

                if overlap:
                    score += min(overlap / len(wanted), 1.0) * 0.8

        return round(score, 4)

    def rank(self, query: str = "", limit: int = 12) -> list[ContextItem]:
        """Ranked, non-expired context (roadmap: context ranking)."""

        self.expire()

        with self._lock:
            items = [item for item in self._items.values() if not item.expired]

        items.sort(key=lambda item: self.score(item, query), reverse=True)

        return items[:limit]

    # ---------------------------------------------------- compression

    def compress(self, text: str, budget: int) -> str:
        """Shorten a value to fit the budget without cutting mid-word."""

        value = " ".join(str(text or "").split())

        if len(value) <= budget:
            return value

        if budget <= 1:
            return value[:budget]

        clipped = value[: budget - 1]
        space = clipped.rfind(" ")

        if space > budget // 2:
            clipped = clipped[:space]

        return clipped.rstrip() + "\u2026"

    # ---------------------------------------------------- assembly

    def assemble(
        self,
        query: str = "",
        budget: int = DEFAULT_BUDGET,
        refresh: bool = True,
        limit: int = 12,
    ) -> str:
        """One ranked, compressed context block ready for a prompt."""

        if refresh:
            self.collect()

        ranked = self.rank(query, limit=limit)

        if not ranked:
            return ""

        lines: list[str] = ["[CONTEXT]"]
        used = len(lines[0])
        per_item = max(int(budget / max(len(ranked), 1)), 80)

        for item in ranked:
            value = self.compress(item.value, per_item)
            line = f"- ({item.kind}) {item.key}: {value}"

            if used + len(line) > budget:
                break

            lines.append(line)
            used += len(line)

        if len(lines) == 1:
            return ""

        return "\n".join(lines)

    def snapshot(self, query: str = "", limit: int = 12) -> list[dict[str, Any]]:
        """Structured view of the ranked context, for the UI or debugging."""

        return [
            {**item.report(), "score": self.score(item, query)}
            for item in self.rank(query, limit=limit)
        ]

    def status(self) -> dict[str, Any]:
        self.expire()

        with self._lock:
            items = list(self._items.values())

        by_kind: dict[str, int] = {}

        for item in items:
            by_kind[item.kind] = by_kind.get(item.kind, 0) + 1

        return {
            "items": len(items),
            "by_kind": by_kind,
            "providers": sorted(self._providers),
            "kinds_supported": sorted(KINDS),
        }


context_engine = ContextEngine()
