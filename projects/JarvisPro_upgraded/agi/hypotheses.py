"""
==========================================
JARVIS PRO
AGI hypothesis engine
==========================================

Roadmap section 28 (hypothesis engine) and section 10 (causal reasoning).

A hypothesis is a candidate explanation the system holds *provisionally*. It
carries evidence for and against, a confidence derived from that evidence, and
the tests that would discriminate it from its rivals.

The engine is deliberately conservative about causation. :meth:`causal_claim`
will not promote a correlation to a causal link without an intervention - a
test where the cause was actually changed and the effect moved with it. This
is the section 10 requirement that temporal order alone is not causation.

    from agi.hypotheses import hypotheses

    h = hypotheses.create("the build fails because a dependency is missing")
    hypotheses.support(h.id, "pip reported ModuleNotFoundError", strength=0.9)
    hypotheses.ranked()
"""

from __future__ import annotations

import re
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from core.atomic_json import AtomicJSONStore

from .uncertainty import Belief, Evidence

UNTESTED = "untested"
TESTING = "testing"
SUPPORTED = "supported"
REJECTED = "rejected"
CONFIRMED = "confirmed"
ARCHIVED = "archived"

STATUSES = (UNTESTED, TESTING, SUPPORTED, REJECTED, CONFIRMED, ARCHIVED)

# Evidence kinds, ordered by how much they justify a causal claim.
OBSERVATION = "observation"
CORRELATION = "correlation"
SEQUENCE = "sequence"
INTERVENTION = "intervention"

CAUSAL_STRENGTH = {
    OBSERVATION: 0,
    SEQUENCE: 1,
    CORRELATION: 2,
    INTERVENTION: 3,
}


@dataclass
class Hypothesis:
    statement: str
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    status: str = UNTESTED
    prior: float = 0.5
    related_entities: list[str] = field(default_factory=list)
    related_goals: list[str] = field(default_factory=list)
    tests: list[str] = field(default_factory=list)
    cause: str = ""
    effect: str = ""
    created: float = field(default_factory=time.time)
    updated: float = field(default_factory=time.time)
    belief: Belief = field(default_factory=lambda: Belief(True, 0.5))

    @property
    def confidence(self) -> float:
        return self.belief.confidence

    def evidence_kinds(self) -> set[str]:
        kinds = set()

        for item in self.belief.evidence:
            match = re.match(r"^(\w+):", item.source or "")
            kinds.add(match.group(1) if match else OBSERVATION)

        return kinds

    def causal_claim(self) -> dict[str, Any]:
        """What this hypothesis is entitled to claim about causation.

        Returns the strongest warranted label, never more:
        ``unsupported`` < ``sequence`` < ``correlation`` < ``causal``.
        """

        kinds = self.evidence_kinds()

        if not self.cause or not self.effect:
            return {"claim": "not a causal hypothesis", "warranted": False}

        best = max((CAUSAL_STRENGTH.get(k, 0) for k in kinds), default=0)
        supporting = sum(1 for e in self.belief.evidence if e.supports)

        if best >= CAUSAL_STRENGTH[INTERVENTION] and self.confidence >= 0.75:
            label = "causal"
            warranted = True

        elif best >= CAUSAL_STRENGTH[CORRELATION]:
            label = "correlation"
            warranted = False

        elif best >= CAUSAL_STRENGTH[SEQUENCE]:
            label = "sequence"
            warranted = False

        else:
            label = "unsupported"
            warranted = False

        return {
            "cause": self.cause,
            "effect": self.effect,
            "claim": label,
            "warranted": warranted,
            "confidence": self.confidence,
            "observations": supporting,
            "note": (
                "an intervention test is required before this may be called causal"
                if not warranted and label in ("correlation", "sequence")
                else ""
            ),
        }

    def report(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "statement": self.statement,
            "status": self.status,
            "prior": self.prior,
            "confidence": self.confidence,
            "level": self.belief.level(),
            "related_entities": list(self.related_entities),
            "related_goals": list(self.related_goals),
            "tests": list(self.tests),
            "cause": self.cause,
            "effect": self.effect,
            "created": self.created,
            "updated": self.updated,
            "belief": self.belief.to_dict(),
            "evidence_for": sum(1 for e in self.belief.evidence if e.supports),
            "evidence_against": sum(1 for e in self.belief.evidence if not e.supports),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Hypothesis":
        item = cls(
            statement=str(data.get("statement", "")),
            id=str(data.get("id") or uuid.uuid4().hex[:12]),
            status=str(data.get("status", UNTESTED)),
            prior=float(data.get("prior", 0.5)),
            related_entities=list(data.get("related_entities") or []),
            related_goals=list(data.get("related_goals") or []),
            tests=list(data.get("tests") or []),
            cause=str(data.get("cause", "")),
            effect=str(data.get("effect", "")),
            created=float(data.get("created", time.time())),
            updated=float(data.get("updated", time.time())),
        )

        try:
            item.belief = Belief.from_dict(data.get("belief") or {})

        except Exception:
            item.belief = Belief(True, item.prior)

        return item


class HypothesisEngine:
    """Persistent store of candidate explanations."""

    def __init__(self, path: str = "data/agi_hypotheses.json") -> None:
        self._lock = threading.RLock()
        self._store = AtomicJSONStore(path, {})
        self._items: dict[str, Hypothesis] = {}
        self._loaded = False

    # ------------------------------------------------------------- storage

    def _ensure(self) -> None:
        if self._loaded:
            return

        with self._lock:
            if self._loaded:
                return

            for item in (self._store.load() or {}).get("hypotheses", {}).values():
                try:
                    h = Hypothesis.from_dict(item)
                    self._items[h.id] = h

                except Exception:
                    continue

            self._loaded = True

    def save(self) -> None:
        self._ensure()

        with self._lock:
            payload = {
                "hypotheses": {k: v.report() for k, v in self._items.items()},
                "saved": time.time(),
            }

        try:
            self._store.save(payload)

        except Exception:
            pass

    def reload(self) -> "HypothesisEngine":
        with self._lock:
            self._items.clear()
            self._loaded = False

        self._ensure()

        return self

    # ------------------------------------------------------------- CRUD

    def create(
        self,
        statement: str,
        prior: float = 0.5,
        tests: list[str] | None = None,
        entities: list[str] | None = None,
        goals: list[str] | None = None,
        cause: str = "",
        effect: str = "",
    ) -> Hypothesis:
        self._ensure()
        text = str(statement).strip()

        if not text:
            raise ValueError("a hypothesis needs a statement")

        with self._lock:
            for existing in self._items.values():
                if existing.statement.lower() == text.lower() and existing.status != ARCHIVED:
                    return existing

        h = Hypothesis(
            statement=text,
            prior=max(0.05, min(0.95, float(prior))),
            tests=list(tests or []),
            related_entities=list(entities or []),
            related_goals=list(goals or []),
            cause=str(cause),
            effect=str(effect),
        )
        h.belief = Belief(True, h.prior, source="hypothesis")

        with self._lock:
            self._items[h.id] = h

        self.save()

        return h

    def get(self, hypothesis_id: str) -> Hypothesis | None:
        self._ensure()

        return self._items.get(str(hypothesis_id))

    def all(self, status: str = "") -> list[Hypothesis]:
        self._ensure()

        with self._lock:
            return [h for h in self._items.values() if not status or h.status == status]

    # ------------------------------------------------------------- evidence

    def _apply(
        self,
        hypothesis_id: str,
        supports: bool,
        note: str,
        strength: float,
        kind: str,
        verified: bool,
    ) -> Hypothesis | None:
        h = self.get(hypothesis_id)

        if h is None:
            return None

        with self._lock:
            h.belief.support(
                Evidence(
                    source=f"{kind}:{note}"[:200],
                    supports=supports,
                    strength=max(0.0, min(1.0, float(strength))),
                    note=note,
                    verified=verified,
                )
            )
            h.updated = time.time()
            h.status = self._classify(h)

        self.save()

        return h

    def support(
        self,
        hypothesis_id: str,
        note: str,
        strength: float = 0.6,
        kind: str = OBSERVATION,
        verified: bool = False,
    ) -> Hypothesis | None:
        return self._apply(hypothesis_id, True, note, strength, kind, verified)

    def refute(
        self,
        hypothesis_id: str,
        note: str,
        strength: float = 0.6,
        kind: str = OBSERVATION,
        verified: bool = False,
    ) -> Hypothesis | None:
        return self._apply(hypothesis_id, False, note, strength, kind, verified)

    def _classify(self, h: Hypothesis) -> str:
        confidence = h.confidence

        if h.status == ARCHIVED:
            return ARCHIVED

        intervened = INTERVENTION in h.evidence_kinds()

        if confidence >= 0.85 and intervened:
            return CONFIRMED

        if confidence >= 0.7:
            return SUPPORTED

        if confidence <= 0.2:
            return REJECTED

        if h.belief.evidence:
            return TESTING

        return UNTESTED

    def archive(self, hypothesis_id: str) -> Hypothesis | None:
        h = self.get(hypothesis_id)

        if h is None:
            return None

        h.status = ARCHIVED
        h.updated = time.time()
        self.save()

        return h

    # ------------------------------------------------------------- ranking

    def ranked(self, goal: str = "", limit: int = 10) -> list[Hypothesis]:
        """Live hypotheses, most credible first."""

        self._ensure()
        rows = [h for h in self.all() if h.status not in (ARCHIVED, REJECTED)]

        if goal:
            terms = set(re.findall(r"[a-z0-9]+", goal.lower()))

            def relevance(h: Hypothesis) -> float:
                words = set(re.findall(r"[a-z0-9]+", h.statement.lower()))
                overlap = len(terms & words) / max(1, len(terms | words))
                linked = 0.2 if goal in h.related_goals else 0.0

                return h.confidence + overlap + linked

            rows.sort(key=relevance, reverse=True)

        else:
            rows.sort(key=lambda h: h.confidence, reverse=True)

        return rows[: int(limit)]

    def most_informative(self, limit: int = 5) -> list[Hypothesis]:
        """Hypotheses worth testing next.

        Maximum information comes from the ones nearest 50/50: confirming or
        refuting those changes the picture most. A hypothesis already at 0.95
        teaches nothing when tested again.
        """

        self._ensure()
        rows = [
            h
            for h in self.all()
            if h.status in (UNTESTED, TESTING, SUPPORTED) and h.tests
        ]
        rows.sort(key=lambda h: abs(h.confidence - 0.5))

        return rows[: int(limit)]

    def discriminating_test(self, a: str, b: str) -> dict[str, Any]:
        """Find a test that separates two rival hypotheses (section 77.8)."""

        first = self.get(a)
        second = self.get(b)

        if not first or not second:
            return {"found": False, "reason": "unknown hypothesis"}

        unique_first = [t for t in first.tests if t not in second.tests]
        unique_second = [t for t in second.tests if t not in first.tests]

        if not unique_first and not unique_second:
            return {
                "found": False,
                "reason": "both hypotheses predict the same observations; "
                "a new test must be designed",
                "shared_tests": list(set(first.tests) & set(second.tests)),
            }

        return {
            "found": True,
            "test": (unique_first or unique_second)[0],
            "distinguishes": first.id if unique_first else second.id,
            "rules_out": second.id if unique_first else first.id,
            "rationale": (
                "this observation is predicted by one hypothesis and not the other"
            ),
        }

    def status(self) -> dict[str, Any]:
        self._ensure()
        rows = self.all()
        counts: dict[str, int] = {}

        for h in rows:
            counts[h.status] = counts.get(h.status, 0) + 1

        return {
            "total": len(rows),
            "by_status": counts,
            "confirmed_causal": sum(
                1 for h in rows if h.causal_claim().get("warranted")
            ),
        }


hypotheses = HypothesisEngine()
