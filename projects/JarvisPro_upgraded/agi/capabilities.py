"""
==========================================
JARVIS PRO
AGI capability registry
==========================================

Roadmap sections 31 (internal state modelling), 45 (capability discovery) and
46 (capability expansion).

This answers, from real state rather than a hand-written list, the questions
section 45 requires:

    What can I do?
    Which tool or manager does it?
    What are the prerequisites?
    How reliable is it?

Capabilities are *discovered* by reflecting over the live
:mod:`tools.registry`, not declared. If a tool fails to register - which
``ToolRegistry.bootstrap`` records in ``registry.errors`` - the capability is
reported as unavailable with the real reason, so the planner can route around
it instead of planning a step that cannot run.

Expansion (section 46) is gated: a newly constructed capability must pass a
policy check and cannot silently acquire a risk class above the tools it is
built from.

    from agi.capabilities import capabilities

    capabilities.discover()
    capabilities.can("open a website")
    capabilities.gaps("send a whatsapp message to my brother")
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any

from core.atomic_json import AtomicJSONStore
from security.policy_engine import policy

from .strategies import keywords

RISK_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}

# Action verbs mapped to the tool categories that can serve them. Used to spot
# a capability gap from a natural request without exact command matching.
INTENT_CATEGORIES: dict[str, tuple[str, ...]] = {
    "open": ("automation", "browser", "desktop"),
    "launch": ("automation", "desktop"),
    "close": ("automation", "desktop"),
    "search": ("browser", "research", "integration"),
    "browse": ("browser",),
    "read": ("file", "document"),
    "write": ("file", "document"),
    "delete": ("file",),
    "move": ("file",),
    "organise": ("file",),
    "organize": ("file",),
    "send": ("messaging", "integration"),
    "message": ("messaging",),
    "remind": ("productivity", "time"),
    "schedule": ("productivity", "time"),
    "time": ("time",),
    "calculate": ("math", "general"),
    "translate": ("language",),
    "code": ("coding",),
    "test": ("coding", "verification"),
    "control": ("iot", "automation"),
    "play": ("media",),
}


@dataclass
class Capability:
    """Something the system can actually do, with evidence for the claim."""

    name: str
    provider: str
    kind: str = "tool"
    description: str = ""
    category: str = "general"
    risk_level: str = "low"
    prerequisites: list[str] = field(default_factory=list)
    permissions: tuple[str, ...] = field(default_factory=tuple)
    available: bool = True
    unavailable_reason: str = ""
    attempts: int = 0
    successes: int = 0
    last_used: float = 0.0
    source: str = "discovered"

    @property
    def reliability(self) -> float:
        """Measured, not asserted. Unknown until it has been used."""

        if not self.attempts:
            return 0.0

        return round(self.successes / self.attempts, 4)

    @property
    def confidence(self) -> str:
        if not self.attempts:
            return "untested"

        if self.attempts < 3:
            return "provisional"

        return "reliable" if self.reliability >= 0.7 else "unreliable"

    def report(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "provider": self.provider,
            "kind": self.kind,
            "description": self.description,
            "category": self.category,
            "risk_level": self.risk_level,
            "prerequisites": list(self.prerequisites),
            "permissions": list(self.permissions),
            "available": self.available,
            "unavailable_reason": self.unavailable_reason,
            "attempts": self.attempts,
            "successes": self.successes,
            "reliability": self.reliability,
            "confidence": self.confidence,
            "last_used": self.last_used,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Capability":
        return cls(
            name=str(data.get("name", "")),
            provider=str(data.get("provider", "")),
            kind=str(data.get("kind", "tool")),
            description=str(data.get("description", "")),
            category=str(data.get("category", "general")),
            risk_level=str(data.get("risk_level", "low")),
            prerequisites=list(data.get("prerequisites") or []),
            permissions=tuple(data.get("permissions") or ()),
            available=bool(data.get("available", True)),
            unavailable_reason=str(data.get("unavailable_reason", "")),
            attempts=int(data.get("attempts", 0)),
            successes=int(data.get("successes", 0)),
            last_used=float(data.get("last_used", 0.0)),
            source=str(data.get("source", "discovered")),
        )


class CapabilityRegistry:
    """Self-knowledge about what this system can do right now."""

    def __init__(self, path: str = "data/agi_capabilities.json") -> None:
        self._lock = threading.RLock()
        self._store = AtomicJSONStore(path, {})
        self._items: dict[str, Capability] = {}
        self._loaded = False
        self._discovered_at = 0.0

    # ------------------------------------------------------------- storage

    def _ensure(self) -> None:
        if self._loaded:
            return

        with self._lock:
            if self._loaded:
                return

            data = self._store.load() or {}

            for item in (data.get("capabilities") or {}).values():
                try:
                    c = Capability.from_dict(item)
                    self._items[c.name] = c

                except Exception:
                    continue

            self._discovered_at = float(data.get("discovered_at", 0.0))
            self._loaded = True

    def save(self) -> None:
        with self._lock:
            payload = {
                "capabilities": {k: v.report() for k, v in self._items.items()},
                "discovered_at": self._discovered_at,
                "saved": time.time(),
            }

        try:
            self._store.save(payload)

        except Exception:
            pass

    # ------------------------------------------------------------- discovery

    def discover(self, registry: Any = None, bootstrap: bool = True) -> dict[str, Any]:
        """Reflect over the live tool registry to learn what exists.

        Reliability counters survive re-discovery; only the availability and
        metadata are refreshed, so measured history is never reset by a
        restart.
        """

        self._ensure()

        if registry is None:
            try:
                from tools.registry import registry

            except Exception as exc:
                return {"ok": False, "reason": f"tool registry unavailable: {exc}"}

        if bootstrap:
            try:
                registry.bootstrap()

            except Exception:
                pass

        found = 0
        refreshed = 0

        try:
            tools = registry.list_tools()

        except Exception as exc:
            return {"ok": False, "reason": f"cannot list tools: {exc}"}

        for tool in tools:
            with self._lock:
                existing = self._items.get(tool.name)

                if existing is None:
                    self._items[tool.name] = Capability(
                        name=tool.name,
                        provider=f"tools.registry:{tool.name}",
                        kind="tool",
                        description=getattr(tool, "description", "") or tool.name,
                        category=getattr(tool, "category", "general"),
                        risk_level=getattr(tool, "risk_level", "low"),
                        permissions=tuple(getattr(tool, "permissions", ()) or ()),
                        available=bool(getattr(tool, "enabled", True)),
                    )
                    found += 1

                else:
                    existing.description = getattr(tool, "description", "") or existing.description
                    existing.category = getattr(tool, "category", existing.category)
                    existing.risk_level = getattr(tool, "risk_level", existing.risk_level)
                    existing.available = bool(getattr(tool, "enabled", True))
                    existing.unavailable_reason = "" if existing.available else "tool disabled"
                    refreshed += 1

        # Tools that failed to load are real capability gaps with real reasons.
        failures = 0

        for error in getattr(registry, "errors", []) or []:
            name = str(error.get("tool", ""))

            if not name:
                continue

            with self._lock:
                capability = self._items.get(name)

                if capability is None:
                    capability = Capability(
                        name=name,
                        provider=f"tools.registry:{name}",
                        description=f"declared but failed to load",
                    )
                    self._items[name] = capability

                capability.available = False
                capability.unavailable_reason = str(error.get("error", "failed to load"))

            failures += 1

        with self._lock:
            self._discovered_at = time.time()

        self.save()

        return {
            "ok": True,
            "discovered": found,
            "refreshed": refreshed,
            "unavailable": failures,
            "total": len(self._items),
        }

    # ------------------------------------------------------------- queries

    def get(self, name: str) -> Capability | None:
        self._ensure()

        return self._items.get(str(name))

    def all(self, available_only: bool = False) -> list[Capability]:
        self._ensure()

        with self._lock:
            return [
                c for c in self._items.values() if not available_only or c.available
            ]

    def can(self, request: str, limit: int = 5) -> list[dict[str, Any]]:
        """Which capabilities could serve this request, best first."""

        self._ensure()
        terms = keywords(request)

        if not terms:
            return []

        wanted_categories: set[str] = set()

        for verb, categories in INTENT_CATEGORIES.items():
            if verb in terms or verb in str(request).lower():
                wanted_categories.update(categories)

        scored: list[tuple[float, Capability, str]] = []

        for capability in self.all():
            words = keywords(f"{capability.name} {capability.description} {capability.category}")
            overlap = len(terms & words) / max(1, len(terms))
            category_hit = 0.35 if capability.category in wanted_categories else 0.0

            if overlap <= 0 and not category_hit:
                continue

            score = 0.55 * overlap + category_hit + 0.1 * capability.reliability

            if not capability.available:
                score *= 0.25

            reason = f"name/description overlap {overlap:.2f}"

            if category_hit:
                reason += f"; category '{capability.category}' fits the request"

            if not capability.available:
                reason += f"; UNAVAILABLE: {capability.unavailable_reason}"

            scored.append((round(score, 4), capability, reason))

        scored.sort(key=lambda row: row[0], reverse=True)

        return [
            {
                "capability": c.name,
                "score": score,
                "available": c.available,
                "reliability": c.reliability,
                "confidence": c.confidence,
                "risk_level": c.risk_level,
                "reason": reason,
            }
            for score, c, reason in scored[: int(limit)]
        ]

    def gaps(self, request: str) -> dict[str, Any]:
        """Decide whether this request exceeds what the system can currently do.

        This is the section 46 entry point and the honest answer to "do I know
        how to do this?" - it distinguishes *no capability at all* from *the
        capability exists but is broken right now*.
        """

        matches = self.can(request, limit=5)
        usable = [m for m in matches if m["available"] and m["score"] >= 0.3]
        broken = [m for m in matches if not m["available"]]

        if usable:
            return {
                "gap": False,
                "best": usable[0]["capability"],
                "candidates": usable,
                "reason": "an available capability matches this request",
            }

        if broken:
            return {
                "gap": True,
                "kind": "unavailable",
                "candidates": broken,
                "reason": (
                    f"the matching capability '{broken[0]['capability']}' exists but "
                    f"is not usable: {broken[0]['reason'].split('UNAVAILABLE: ')[-1]}"
                ),
                "next": "repair or substitute the provider before planning this step",
            }

        return {
            "gap": True,
            "kind": "missing",
            "candidates": matches,
            "reason": "no registered capability matches this request",
            "next": "construct a procedure from existing capabilities, or ask the human",
        }

    # ------------------------------------------------------------- outcomes

    def record_outcome(self, name: str, success: bool) -> Capability | None:
        capability = self.get(name)

        if capability is None:
            return None

        with self._lock:
            capability.attempts += 1
            capability.successes += int(bool(success))
            capability.last_used = time.time()

        self.save()

        return capability

    def mark_unavailable(self, name: str, reason: str) -> Capability | None:
        capability = self.get(name)

        if capability is None:
            return None

        with self._lock:
            capability.available = False
            capability.unavailable_reason = str(reason)

        self.save()

        return capability

    # ------------------------------------------------------------- expansion

    def expand(
        self,
        name: str,
        description: str,
        built_from: list[str],
        procedure: list[str],
        approved_by: str = "",
    ) -> dict[str, Any]:
        """Register a capability composed from existing ones (section 46).

        Two guards, enforced here rather than by prompt:

        * the composite inherits the *highest* risk of its parts, so it cannot
          launder a high-risk action into a low-risk wrapper;
        * a resulting high or critical risk class requires explicit human
          approval before the capability is registered at all.
        """

        self._ensure()

        if self.get(name) is not None:
            return {"ok": False, "reason": f"capability already exists: {name}"}

        if not built_from:
            return {"ok": False, "reason": "a new capability must be built from existing ones"}

        parts: list[Capability] = []

        for part in built_from:
            found = self.get(part)

            if found is None:
                return {
                    "ok": False,
                    "reason": f"cannot build on unknown capability: {part}",
                }

            if not found.available:
                return {
                    "ok": False,
                    "reason": f"component '{part}' is unavailable: {found.unavailable_reason}",
                }

            parts.append(found)

        inherited = max(parts, key=lambda c: RISK_ORDER.get(c.risk_level, 1))
        risk = inherited.risk_level

        action = {
            "low": "read",
            "medium": "file.write",
            "high": "code.execute",
            "critical": "system.shutdown",
        }.get(risk, "file.write")

        decision = policy.check(action, {"capability": name, "composed_of": built_from})

        if not decision.allowed and not approved_by:
            return {
                "ok": False,
                "needs_approval": True,
                "risk_level": risk,
                "reason": (
                    f"composing {built_from} yields risk '{risk}': {decision.reason}"
                ),
                "inherited_from": inherited.name,
            }

        permissions: set[str] = set()

        for part in parts:
            permissions.update(part.permissions)

        capability = Capability(
            name=str(name),
            provider="agi.capabilities:composed",
            kind="composite",
            description=str(description),
            category="composed",
            risk_level=risk,
            prerequisites=list(built_from),
            permissions=tuple(sorted(permissions)),
            available=True,
            source="expanded" if not approved_by else f"expanded (approved by {approved_by})",
        )

        with self._lock:
            self._items[capability.name] = capability

        self.save()

        return {
            "ok": True,
            "capability": capability.report(),
            "procedure": list(procedure),
            "risk_level": risk,
            "inherited_from": inherited.name,
            "approved_by": approved_by,
        }

    # ------------------------------------------------------------- self-state

    def self_report(self) -> dict[str, Any]:
        """Section 31: what am I able to do, and how sure am I?"""

        rows = self.all()
        by_category: dict[str, int] = {}

        for capability in rows:
            by_category[capability.category] = by_category.get(capability.category, 0) + 1

        return {
            "total": len(rows),
            "available": sum(1 for c in rows if c.available),
            "unavailable": [
                {"name": c.name, "reason": c.unavailable_reason}
                for c in rows
                if not c.available
            ],
            "untested": sum(1 for c in rows if c.confidence == "untested"),
            "reliable": sum(1 for c in rows if c.confidence == "reliable"),
            "unreliable": [c.name for c in rows if c.confidence == "unreliable"],
            "by_category": by_category,
            "by_risk": {
                level: sum(1 for c in rows if c.risk_level == level)
                for level in RISK_ORDER
            },
            "last_discovery": self._discovered_at,
        }

    def status(self) -> dict[str, Any]:
        rows = self.all()

        return {
            "total": len(rows),
            "available": sum(1 for c in rows if c.available),
            "composite": sum(1 for c in rows if c.kind == "composite"),
        }


capabilities = CapabilityRegistry()
