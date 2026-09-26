"""
==========================================
JARVIS PRO
AGI uncertainty engine
==========================================

Roadmap section 41: uncertainty-aware reasoning.

Nothing in the AGI layer is allowed to return a bare value for anything it
inferred. It returns a :class:`Belief`: the value, how confident the system is,
what evidence produced that confidence, and which assumptions it rests on.

    from agi.uncertainty import Belief, Evidence, combine

    b = Belief("chrome is running", 0.5)
    b.support(Evidence("process list", True, 0.9))
    b.confidence      # rises
    b.level()         # "likely"

Confidence is *computed* from evidence, never assigned as a decoration. A
belief with no evidence stays at its prior and reports ``unknown``.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any, Iterable

# Confidence bands used across the AGI layer. Section 33 requires the system to
# distinguish KNOWN / LIKELY / UNCERTAIN / UNKNOWN rather than emit a number.
KNOWN = "known"
LIKELY = "likely"
UNCERTAIN = "uncertain"
UNKNOWN = "unknown"

# Below this, the AGI must ask a human rather than act (section 63).
ASK_HUMAN_BELOW = 0.35

# Evidence older than this loses weight (section 38: confidence decay).
DEFAULT_HALF_LIFE = 7 * 24 * 3600.0


@dataclass
class Evidence:
    """One observation bearing on a belief."""

    source: str
    supports: bool = True
    strength: float = 0.5
    note: str = ""
    verified: bool = False
    at: float = field(default_factory=time.time)

    def weight(self, half_life: float = DEFAULT_HALF_LIFE, now: float | None = None) -> float:
        """Strength after time decay. Verified evidence decays half as fast."""

        now = time.time() if now is None else now
        age = max(0.0, now - self.at)
        life = half_life * (2.0 if self.verified else 1.0)
        decay = 0.5 ** (age / life) if life > 0 else 1.0

        return max(0.0, min(1.0, float(self.strength))) * decay

    def report(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "supports": self.supports,
            "strength": round(float(self.strength), 3),
            "verified": self.verified,
            "note": self.note,
            "at": self.at,
        }


@dataclass
class Belief:
    """A value the AGI holds with a confidence it can justify."""

    value: Any
    prior: float = 0.5
    evidence: list[Evidence] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    source: str = "inference"
    updated: float = field(default_factory=time.time)
    # Set by whoever holds the belief (the world model) to express how much
    # the passage of time has eroded it. 1.0 is freshly observed, 0.0 is
    # wholly untrustworthy. Kept separate from evidence so that ageing never
    # corrupts the record of what was actually observed.
    freshness: float = 1.0

    # ------------------------------------------------------------ updates

    def support(self, evidence: Evidence) -> "Belief":
        self.evidence.append(evidence)
        self.updated = time.time()

        return self

    def refute(self, evidence: Evidence) -> "Belief":
        evidence.supports = False

        return self.support(evidence)

    def assume(self, assumption: str) -> "Belief":
        """Record an unverified premise. Assumptions cap confidence."""

        text = str(assumption).strip()

        if text and text not in self.assumptions:
            self.assumptions.append(text)

        return self

    # ------------------------------------------------------------ readout

    @property
    def confidence(self) -> float:
        """Log-odds accumulation of evidence over the prior.

        Each piece of evidence shifts the odds rather than averaging into the
        value, so ten weak confirmations do not outweigh one strong refutation
        as crudely as a mean would.
        """

        prior = min(0.99, max(0.01, float(self.prior)))
        odds = math.log(prior / (1 - prior))

        for item in self.evidence:
            weight = item.weight()

            if weight <= 0:
                continue

            # Cap a single piece of evidence so nothing becomes certain alone.
            shift = min(2.2, weight * 2.5)
            odds += shift if item.supports else -shift

        value = 1 / (1 + math.exp(-odds))

        # Unverified assumptions cap how sure the system is allowed to be.
        # The factor is 0.8 rather than 0.85 so that a single assumption lands
        # *below* the KNOWN threshold: at 0.85 a stale fact sat exactly on the
        # boundary and was still reported as known, which is the failure mode
        # the staleness machinery exists to prevent.
        #
        # Staleness notes are excluded from the count. They are recorded for
        # explanation, but the numeric penalty for ageing is carried by
        # ``freshness`` below - counting them here charged for the same thing
        # twice and drove recent observations down to near zero.
        premises = [a for a in self.assumptions if not a.startswith("not re-observed")]

        if premises:
            value = min(value, 0.8 ** len(premises))

        # Ageing erodes confidence proportionally, so a fact long past its
        # freshness window is far weaker than one just past it.
        value *= max(0.0, min(1.0, float(self.freshness)))

        return round(max(0.0, min(1.0, value)), 4)

    def level(self) -> str:
        confidence = self.confidence

        if not self.evidence and abs(confidence - 0.5) < 0.05:
            return UNKNOWN

        # An observation too old to be worth anything is not "uncertain
        # knowledge" - it is an absence of current knowledge.
        if self.freshness < 0.15:
            return UNKNOWN

        if confidence >= 0.85:
            return KNOWN

        if confidence >= 0.6:
            return LIKELY

        if confidence <= 0.15:
            return KNOWN if self.value in (False, None) else UNCERTAIN

        return UNCERTAIN

    def needs_human(self) -> bool:
        """True when the system is too unsure to act on its own.

        A belief resting on no evidence at all counts, not only one with low
        confidence: an untouched prior of 0.5 sits above the numeric floor, but
        knowing nothing is precisely the case where a human should be asked.
        """

        return self.confidence < ASK_HUMAN_BELOW or self.level() == UNKNOWN

    def stale(self, max_age: float = DEFAULT_HALF_LIFE) -> bool:
        return (time.time() - self.updated) > max_age

    def report(self) -> dict[str, Any]:
        return {
            "value": self.value,
            "confidence": self.confidence,
            "level": self.level(),
            "source": self.source,
            "assumptions": list(self.assumptions),
            "evidence": [e.report() for e in self.evidence],
            "updated": self.updated,
        }

    def explain(self) -> str:
        """Human-readable justification built from real state, not a template."""

        parts = [f"{self.value!r} is {self.level()} (confidence {self.confidence:.2f})"]

        for_count = sum(1 for e in self.evidence if e.supports)
        against = len(self.evidence) - for_count

        if self.evidence:
            parts.append(f"{for_count} supporting and {against} opposing observation(s)")

        else:
            parts.append("no evidence gathered yet")

        if self.assumptions:
            parts.append("resting on unverified assumptions: " + "; ".join(self.assumptions))

        return "; ".join(parts)

    # ------------------------------------------------------------ storage

    def to_dict(self) -> dict[str, Any]:
        return {
            "value": self.value,
            "prior": self.prior,
            "assumptions": list(self.assumptions),
            "source": self.source,
            "updated": self.updated,
            "freshness": self.freshness,
            "evidence": [e.report() for e in self.evidence],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Belief":
        belief = cls(
            value=data.get("value"),
            prior=float(data.get("prior", 0.5)),
            assumptions=list(data.get("assumptions") or []),
            source=str(data.get("source", "inference")),
            updated=float(data.get("updated", time.time())),
            freshness=float(data.get("freshness", 1.0)),
        )

        for item in data.get("evidence") or []:
            belief.evidence.append(
                Evidence(
                    source=str(item.get("source", "")),
                    supports=bool(item.get("supports", True)),
                    strength=float(item.get("strength", 0.5)),
                    note=str(item.get("note", "")),
                    verified=bool(item.get("verified", False)),
                    at=float(item.get("at", time.time())),
                )
            )

        return belief


def combine(beliefs: Iterable[Belief], mode: str = "all") -> float:
    """Propagate confidence through a conjunction or disjunction.

    ``all``  - every belief must hold (a plan step chain): multiply.
    ``any``  - one is enough (alternative routes): noisy-OR.
    """

    values = [b.confidence for b in beliefs]

    if not values:
        return 0.0

    if mode == "any":
        product = 1.0

        for value in values:
            product *= (1 - value)

        return round(1 - product, 4)

    product = 1.0

    for value in values:
        product *= value

    return round(product, 4)


def ambiguous(options: dict[str, float], margin: float = 0.15) -> bool:
    """True when the top two candidates are too close to choose between.

    Used by intent understanding to decide whether to ask the user instead of
    guessing (section 63: ask when ambiguity is dangerous).
    """

    if len(options) < 2:
        return False

    ranked = sorted(options.values(), reverse=True)

    return (ranked[0] - ranked[1]) < margin
