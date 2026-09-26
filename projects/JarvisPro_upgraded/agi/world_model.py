"""
==========================================
JARVIS PRO
AGI world model
==========================================

Roadmap sections 30 (world model), 32 (environment modelling), 33 (causal world
understanding), 57 (environment + reasoning) and 60 (persistence).

The world model is what JARVIS believes is currently true about the machine,
the applications, the files and the projects it works with. Three rules shape
the whole design:

1. Every fact is a :class:`~agi.uncertainty.Belief`, never a bare value, so the
   planner can tell KNOWN from LIKELY from UNKNOWN.
2. Facts go stale. A fact observed twenty minutes ago is not reported as
   current truth; :meth:`get` downgrades it and :meth:`stale` lists what needs
   re-checking. This is the "do not let stale state masquerade as current
   truth" requirement.
3. Only *observations* raise confidence. Writing an intention into the model
   does not make it true - :meth:`observe` is separate from :meth:`assume`.

    from agi.world_model import world

    world.observe("chrome", "running", True, source="process list")
    world.get("chrome", "running").level()        # "known"
    world.relate("jarvis", "edits", "project:JarvisPro")
"""

from __future__ import annotations

import threading
import time
from typing import Any, Iterable

from core.atomic_json import AtomicJSONStore

from .uncertainty import Belief, Evidence

# How long a property stays trustworthy before it must be re-observed.
# Process state changes constantly; a file's existence is stable for longer.
FRESHNESS: dict[str, float] = {
    "process": 60.0,
    "window": 60.0,
    "running": 60.0,
    "focused": 30.0,
    "network": 120.0,
    "memory": 120.0,
    "cpu": 60.0,
    "file": 600.0,
    "exists": 600.0,
    "path": 1800.0,
    "project": 1800.0,
    "installed": 86400.0,
    "device": 3600.0,
    "preference": 604800.0,
}

DEFAULT_FRESHNESS = 900.0

# Entity kinds the model knows how to hold (section 30).
KINDS = (
    "application",
    "process",
    "file",
    "folder",
    "project",
    "device",
    "service",
    "person",
    "network",
    "system",
    "task",
    "resource",
    "concept",
)


def freshness_for(prop: str) -> float:
    name = str(prop).lower()

    for key, seconds in FRESHNESS.items():
        if key in name:
            return seconds

    return DEFAULT_FRESHNESS


class Entity:
    """One thing in the world, with beliefs about its properties."""

    def __init__(self, name: str, kind: str = "concept") -> None:
        self.name = str(name)
        self.kind = kind if kind in KINDS else "concept"
        self.properties: dict[str, Belief] = {}
        self.created = time.time()

    def set(self, prop: str, belief: Belief) -> None:
        self.properties[str(prop)] = belief

    def report(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind,
            "created": self.created,
            "properties": {k: v.to_dict() for k, v in self.properties.items()},
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Entity":
        entity = cls(data.get("name", ""), data.get("kind", "concept"))
        entity.created = float(data.get("created", time.time()))

        for key, value in (data.get("properties") or {}).items():
            try:
                entity.properties[key] = Belief.from_dict(value)

            except Exception:
                continue

        return entity


class WorldModel:
    """Persistent, confidence-aware model of the environment."""

    def __init__(self, path: str = "data/agi_world.json") -> None:
        self._lock = threading.RLock()
        self._store = AtomicJSONStore(path, {})
        self._entities: dict[str, Entity] = {}
        self._relations: list[dict[str, Any]] = []
        self._events: list[dict[str, Any]] = []
        self._loaded = False

    # ------------------------------------------------------------ storage

    def _ensure(self) -> None:
        if self._loaded:
            return

        with self._lock:
            if self._loaded:
                return

            data = self._store.load() or {}

            for item in (data.get("entities") or {}).values():
                try:
                    entity = Entity.from_dict(item)
                    self._entities[entity.name.lower()] = entity

                except Exception:
                    continue

            self._relations = [r for r in (data.get("relations") or []) if isinstance(r, dict)]
            self._events = [e for e in (data.get("events") or []) if isinstance(e, dict)]
            self._loaded = True

    def save(self) -> None:
        self._ensure()

        with self._lock:
            payload = {
                "entities": {k: v.report() for k, v in self._entities.items()},
                "relations": self._relations[-500:],
                "events": self._events[-300:],
                "saved": time.time(),
            }

        try:
            self._store.save(payload)

        except Exception:
            pass

    def reload(self) -> "WorldModel":
        """Force a re-read from disk. Used to prove restart persistence."""

        with self._lock:
            self._entities.clear()
            self._relations.clear()
            self._events.clear()
            self._loaded = False

        self._ensure()

        return self

    # ------------------------------------------------------------ entities

    def entity(self, name: str, kind: str = "concept") -> Entity:
        self._ensure()
        key = str(name).lower()

        with self._lock:
            found = self._entities.get(key)

            if found is None:
                found = Entity(name, kind)
                self._entities[key] = found

            elif kind != "concept" and found.kind == "concept":
                found.kind = kind if kind in KINDS else found.kind

            return found

    def observe(
        self,
        name: str,
        prop: str,
        value: Any,
        source: str = "observation",
        strength: float = 0.8,
        kind: str = "concept",
        verified: bool = True,
    ) -> Belief:
        """Record something actually seen. This is the only high-trust path in.

        A *new* value for a property replaces the old belief rather than
        averaging with it - the world changed, the old evidence is about a
        state that no longer holds.
        """

        entity = self.entity(name, kind)
        key = str(prop)

        with self._lock:
            current = entity.properties.get(key)

            if current is not None and current.value == value:
                current.support(
                    Evidence(source, True, float(strength), verified=verified)
                )
                current.updated = time.time()
                belief = current

            else:
                if current is not None:
                    self._record_event(
                        "state_change",
                        entity=entity.name,
                        prop=key,
                        was=current.value,
                        now=value,
                        source=source,
                    )

                belief = Belief(value, prior=0.5, source=source)
                belief.support(Evidence(source, True, float(strength), verified=verified))
                entity.set(key, belief)

        self.save()

        return belief

    def assume(
        self,
        name: str,
        prop: str,
        value: Any,
        reason: str = "assumption",
        kind: str = "concept",
    ) -> Belief:
        """Record an *unverified* expectation. Confidence stays capped."""

        entity = self.entity(name, kind)
        belief = Belief(value, prior=0.5, source="assumption")
        belief.assume(reason)

        with self._lock:
            existing = entity.properties.get(str(prop))

            # Never let an assumption overwrite something actually observed.
            if existing is not None and existing.confidence > 0.6:
                return existing

            entity.set(str(prop), belief)

        self.save()

        return belief

    def contradict(
        self,
        name: str,
        prop: str,
        source: str = "observation",
        strength: float = 0.8,
    ) -> Belief | None:
        """Record evidence *against* the currently held value."""

        entity = self.entity(name)
        belief = entity.properties.get(str(prop))

        if belief is None:
            return None

        belief.refute(Evidence(source, False, float(strength), verified=True))
        belief.updated = time.time()
        self._record_event("contradiction", entity=name, prop=str(prop), source=source)
        self.save()

        return belief

    def get(self, name: str, prop: str) -> Belief | None:
        """Current belief, with staleness already applied.

        A stale belief is returned with an explicit staleness assumption
        attached, which lowers its confidence - so a caller that trusts
        ``level()`` cannot accidentally treat old state as current truth.
        """

        self._ensure()
        entity = self._entities.get(str(name).lower())

        if entity is None:
            return None

        belief = entity.properties.get(str(prop))

        if belief is None:
            return None

        age = time.time() - belief.updated
        window = freshness_for(prop)

        if age > window:
            # Decay by how far *past* the window the fact is, not by its total
            # age: a fact that has just crossed the line is still broadly
            # trustworthy, one many windows past it is not. Measuring from
            # zero age instead charged a two-minute-old observation as though
            # it were hours stale.
            excess = (age - window) / window
            belief.freshness = round(max(0.05, 0.7 ** excess), 4)

            note = f"not re-observed for {int(age)}s"

            # Replace any older staleness note rather than stacking them.
            belief.assumptions = [
                a for a in belief.assumptions if not a.startswith("not re-observed")
            ]
            belief.assume(note)

        else:
            belief.freshness = 1.0

        return belief

    def value(self, name: str, prop: str, default: Any = None) -> Any:
        belief = self.get(name, prop)

        return default if belief is None else belief.value

    def known(self, name: str, prop: str) -> bool:
        belief = self.get(name, prop)

        return bool(belief and belief.level() == "known")

    def forget(self, name: str) -> bool:
        self._ensure()

        with self._lock:
            removed = self._entities.pop(str(name).lower(), None) is not None
            self._relations = [
                r
                for r in self._relations
                if r.get("subject", "").lower() != str(name).lower()
                and r.get("object", "").lower() != str(name).lower()
            ]

        if removed:
            self.save()

        return removed

    # ------------------------------------------------------------ relations

    def relate(
        self,
        subject: str,
        predicate: str,
        obj: str,
        confidence: float = 0.7,
        source: str = "observation",
    ) -> dict[str, Any]:
        self._ensure()
        record = {
            "subject": str(subject),
            "predicate": str(predicate),
            "object": str(obj),
            "confidence": round(max(0.0, min(1.0, float(confidence))), 3),
            "source": source,
            "at": time.time(),
        }

        with self._lock:
            for existing in self._relations:
                if (
                    existing.get("subject") == record["subject"]
                    and existing.get("predicate") == record["predicate"]
                    and existing.get("object") == record["object"]
                ):
                    existing["confidence"] = round(
                        min(1.0, existing.get("confidence", 0.5) + 0.1), 3
                    )
                    existing["at"] = record["at"]
                    self.save()

                    return existing

            self._relations.append(record)

        self.save()

        return record

    def relations(
        self, subject: str = "", predicate: str = "", obj: str = ""
    ) -> list[dict[str, Any]]:
        self._ensure()

        def matches(row: dict[str, Any]) -> bool:
            if subject and row.get("subject", "").lower() != subject.lower():
                return False

            if predicate and row.get("predicate", "").lower() != predicate.lower():
                return False

            if obj and row.get("object", "").lower() != obj.lower():
                return False

            return True

        with self._lock:
            return [dict(r) for r in self._relations if matches(r)]

    def depends_on(self, name: str, depth: int = 3) -> list[str]:
        """Transitive dependency closure - what breaks if ``name`` breaks."""

        seen: set[str] = set()
        frontier = [str(name)]

        for _ in range(max(1, depth)):
            nxt: list[str] = []

            for item in frontier:
                for row in self.relations(obj=item):
                    if row.get("predicate") in ("depends_on", "requires", "uses"):
                        subject = row.get("subject", "")

                        if subject and subject.lower() not in seen:
                            seen.add(subject.lower())
                            nxt.append(subject)

            frontier = nxt

            if not frontier:
                break

        return sorted(seen)

    # ------------------------------------------------------------ events

    def _record_event(self, kind: str, **detail: Any) -> None:
        self._events.append({"kind": kind, "at": time.time(), **detail})
        del self._events[:-300]

    def events(self, kind: str = "", limit: int = 50) -> list[dict[str, Any]]:
        self._ensure()

        with self._lock:
            rows = [e for e in self._events if not kind or e.get("kind") == kind]

            return rows[-int(limit):][::-1]

    def changed_since(self, moment: float) -> list[dict[str, Any]]:
        self._ensure()

        with self._lock:
            return [e for e in self._events if float(e.get("at", 0)) > moment]

    # ------------------------------------------------------------ hygiene

    def stale(self) -> list[dict[str, Any]]:
        """Properties that must be re-observed before being trusted."""

        self._ensure()
        now = time.time()
        out: list[dict[str, Any]] = []

        with self._lock:
            for entity in self._entities.values():
                for prop, belief in entity.properties.items():
                    age = now - belief.updated

                    if age > freshness_for(prop):
                        out.append(
                            {
                                "entity": entity.name,
                                "property": prop,
                                "value": belief.value,
                                "age": round(age, 1),
                                "confidence": belief.confidence,
                            }
                        )

        return sorted(out, key=lambda r: r["age"], reverse=True)

    def contradictions(self) -> list[dict[str, Any]]:
        """Beliefs whose evidence points both ways without resolution."""

        self._ensure()
        out: list[dict[str, Any]] = []

        with self._lock:
            for entity in self._entities.values():
                for prop, belief in entity.properties.items():
                    supporting = sum(1 for e in belief.evidence if e.supports)
                    opposing = len(belief.evidence) - supporting

                    if supporting and opposing and 0.25 < belief.confidence < 0.75:
                        out.append(
                            {
                                "entity": entity.name,
                                "property": prop,
                                "supporting": supporting,
                                "opposing": opposing,
                                "confidence": belief.confidence,
                            }
                        )

        return out

    def snapshot(self, kind: str = "") -> dict[str, Any]:
        self._ensure()

        with self._lock:
            entities = {
                name: {
                    "kind": e.kind,
                    "properties": {
                        p: {"value": b.value, "level": b.level(), "confidence": b.confidence}
                        for p, b in e.properties.items()
                    },
                }
                for name, e in self._entities.items()
                if not kind or e.kind == kind
            }

            return {
                "entities": entities,
                "relations": len(self._relations),
                "events": len(self._events),
                "stale": len(self.stale()),
            }

    def status(self) -> dict[str, Any]:
        self._ensure()

        with self._lock:
            facts = sum(len(e.properties) for e in self._entities.values())

            return {
                "entities": len(self._entities),
                "facts": facts,
                "relations": len(self._relations),
                "events": len(self._events),
                "stale_facts": len(self.stale()),
                "contradictions": len(self.contradictions()),
            }


world = WorldModel()
