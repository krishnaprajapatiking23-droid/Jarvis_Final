"""
==========================================
JARVIS PRO
AGI abstraction and transfer
==========================================

Roadmap sections 8 (cross-domain reasoning), 9 (abstract reasoning),
12 (analogical reasoning), 13 (counterfactual reasoning) and 22 (cross-task
knowledge transfer).

The mechanism that makes transfer possible is a small vocabulary of
*problem structures* that are deliberately domain-free:

    resource_conflict, missing_prerequisite, ordering_violation,
    capacity_limit, stale_state, ambiguous_specification, ...

A concrete event is abstracted to one of these, and any lesson attached to the
structure becomes available to every domain. This is the difference the roadmap
draws in section 8 between storing command-response pairs and storing reusable
strategy:

    concrete: "Chrome was unavailable because the process was already running"
    abstract: "resource_conflict - a resource already held causes
               initialisation to fail"

The abstract form then fires on a database connection, a file lock or a port
binding, none of which share vocabulary with the original.
"""

from __future__ import annotations

import copy
import re
import time
from dataclasses import dataclass, field
from typing import Any

from .strategies import keywords, normalise, stem

# Domain-free problem structures. Each has the signals that indicate it and the
# general lesson it licenses.
STRUCTURES: dict[str, dict[str, Any]] = {
    "resource_conflict": {
        "signals": [
            "already", "in use", "locked", "held", "busy", "conflict",
            "duplicate", "exists", "running", "occupied", "port", "taken",
        ],
        "general": "a resource already held causes initialisation to fail; "
                   "check for an existing holder before acquiring",
        "check": "is something already holding the resource?",
        "remedy": "reuse the existing holder, or release it before acquiring",
    },
    "missing_prerequisite": {
        "signals": [
            "missing", "not found", "no such", "absent", "required",
            "notfound", "undefined", "unavailable", "import", "depend",
            "install", "modulenotfound",
        ],
        "general": "an action fails when something it depends on does not exist; "
                   "verify prerequisites before acting, not after",
        "check": "does everything this step depends on exist?",
        "remedy": "create or install the prerequisite, or choose a route that "
                  "does not need it",
    },
    "ordering_violation": {
        "signals": [
            "before", "after", "order", "sequence", "premature", "too early",
            "not ready", "pending", "uninitialised", "first",
        ],
        "general": "steps executed out of order fail even when each is correct "
                   "in isolation; derive the order from the dependencies",
        "check": "is every dependency of this step already complete?",
        "remedy": "reorder by dependency and re-run from the earliest valid step",
    },
    "capacity_limit": {
        "signals": [
            "full", "quota", "limit", "exceed", "out of", "space", "memory",
            "timeout", "too large", "rate", "throttle", "overflow",
        ],
        "general": "a finite resource runs out under load; measure headroom "
                   "before committing to work that consumes it",
        "check": "how much of the limiting resource remains?",
        "remedy": "reduce the batch, free capacity, or switch to a cheaper route",
    },
    "stale_state": {
        "signals": [
            "stale", "outdated", "changed", "moved", "renamed", "cache",
            "no longer", "was", "expired", "mismatch", "drift",
        ],
        "general": "state observed earlier may no longer hold; re-observe before "
                   "acting on remembered state",
        "check": "when was this last actually observed?",
        "remedy": "re-observe, update the model, and replan against what is there now",
    },
    "ambiguous_specification": {
        "signals": [
            "unclear", "ambiguous", "which", "either", "maybe", "some",
            "vague", "unspecified", "assume", "guess",
        ],
        "general": "an underspecified goal produces a plausible but wrong result; "
                   "resolve the ambiguity before planning",
        "check": "could this request mean more than one thing?",
        "remedy": "ask one specific question that separates the readings",
    },
    "permission_boundary": {
        "signals": [
            "permission", "denied", "forbidden", "unauthorised", "unauthorized",
            "access", "privilege", "credential", "auth", "refuse",
        ],
        "general": "an action blocked by policy will not succeed on retry; it "
                   "needs a different route or an authorisation",
        "check": "is this refusal about permission rather than capability?",
        "remedy": "request approval, or achieve the goal by a permitted route",
    },
    "silent_failure": {
        "signals": [
            "nothing happened", "no effect", "silent", "empty", "no output",
            "ignored", "succeeded but", "returned none",
        ],
        "general": "a command that reports success has not necessarily had an "
                   "effect; verify the outcome independently of the return value",
        "check": "was the effect observed, or only the call's return value?",
        "remedy": "add an independent check of the intended effect",
    },
}


@dataclass
class Abstraction:
    """A concrete observation reduced to its domain-free structure."""

    concrete: str
    structure: str
    general: str
    confidence: float
    signals_matched: list[str] = field(default_factory=list)
    domain: str = ""
    at: float = field(default_factory=time.time)

    def report(self) -> dict[str, Any]:
        return {
            "concrete": self.concrete[:300],
            "structure": self.structure,
            "general": self.general,
            "confidence": round(float(self.confidence), 4),
            "signals_matched": list(self.signals_matched),
            "domain": self.domain,
            "at": self.at,
        }


class TransferEngine:
    """Abstraction, analogy and cross-domain transfer."""

    # -------------------------------------------------------- abstraction

    def abstract(self, concrete: str, domain: str = "") -> Abstraction | None:
        """Reduce a concrete event to a domain-free structure (section 9).

        Returns ``None`` when nothing matches - an unrecognised event is not
        forced into a category it does not fit.
        """

        # Phrase signals are checked against the normalised form so compound
        # identifiers such as ModuleNotFoundError ("module not found error")
        # match the "not found" signal instead of being one opaque token.
        text = normalise(concrete)

        if not text.strip():
            return None

        terms = keywords(concrete)
        best: tuple[float, str, list[str]] | None = None

        for name, spec in STRUCTURES.items():
            matched: list[str] = []

            for signal in spec["signals"]:
                if " " in signal:
                    if signal in text:
                        matched.append(signal)

                elif stem(signal) in terms:
                    matched.append(signal)

            if not matched:
                continue

            # Confidence grows with the number of independent signals but is
            # capped: a structural label is a hypothesis, not a fact.
            score = min(0.9, 0.35 + 0.18 * len(matched))

            if best is None or score > best[0]:
                best = (score, name, matched)

        if best is None:
            return None

        score, name, matched = best

        return Abstraction(
            concrete=str(concrete),
            structure=name,
            general=STRUCTURES[name]["general"],
            confidence=score,
            signals_matched=matched,
            domain=domain,
        )

    def structures_for(self, problem: str) -> list[dict[str, Any]]:
        """Every structure that plausibly applies, with its check and remedy."""

        text = normalise(problem)
        terms = keywords(problem)
        out: list[dict[str, Any]] = []

        for name, spec in STRUCTURES.items():
            matched = [
                s for s in spec["signals"]
                if (s in text if " " in s else stem(s) in terms)
            ]

            if not matched:
                continue

            out.append(
                {
                    "structure": name,
                    "confidence": round(min(0.9, 0.35 + 0.18 * len(matched)), 4),
                    "general": spec["general"],
                    "check": spec["check"],
                    "remedy": spec["remedy"],
                    "signals": matched,
                }
            )

        return sorted(out, key=lambda r: r["confidence"], reverse=True)

    # -------------------------------------------------------- analogy

    def map_analogy(
        self, source_problem: str, target_problem: str
    ) -> dict[str, Any]:
        """Structural mapping between two problems (section 12).

        A match on *structure* counts far more than a match on vocabulary,
        which is what lets a lesson move between unrelated domains.
        """

        source = self.abstract(source_problem)
        target = self.abstract(target_problem)

        source_terms = keywords(source_problem)
        target_terms = keywords(target_problem)
        surface = len(source_terms & target_terms) / max(1, len(source_terms | target_terms))

        if source is None or target is None:
            return {
                "mapped": False,
                "reason": (
                    "one of the problems has no recognisable structure, so no "
                    "structural mapping can be made"
                ),
                "surface_similarity": round(surface, 4),
                "source_structure": source.structure if source else None,
                "target_structure": target.structure if target else None,
            }

        if source.structure != target.structure:
            return {
                "mapped": False,
                "reason": (
                    f"the problems have different structures "
                    f"({source.structure} vs {target.structure}); a surface "
                    f"resemblance is not a basis for transfer"
                ),
                "surface_similarity": round(surface, 4),
                "source_structure": source.structure,
                "target_structure": target.structure,
            }

        # Same structure, different vocabulary is the strongest transfer case:
        # it means the match is genuinely structural, not a coincidence of words.
        cross_domain = surface < 0.3
        confidence = round(min(0.9, (source.confidence + target.confidence) / 2), 4)

        return {
            "mapped": True,
            "structure": source.structure,
            "shared_general_lesson": source.general,
            "check": STRUCTURES[source.structure]["check"],
            "transferred_remedy": STRUCTURES[source.structure]["remedy"],
            "confidence": confidence,
            "surface_similarity": round(surface, 4),
            "cross_domain": cross_domain,
            "note": (
                "structure matches while vocabulary does not - this is a genuine "
                "cross-domain transfer"
                if cross_domain
                else "the problems are similar on the surface as well as structurally"
            ),
        }

    def find_analogies(
        self, problem: str, experiences: list[dict[str, Any]], limit: int = 3
    ) -> list[dict[str, Any]]:
        """Search past experience for structurally analogous cases."""

        target = self.abstract(problem)

        if target is None:
            return []

        out: list[dict[str, Any]] = []

        for record in experiences:
            text = " ".join(
                str(record.get(key, ""))
                for key in ("goal", "error", "strategy", "lesson", "content", "concept")
            ).strip()

            if not text:
                continue

            source = self.abstract(text)

            if source is None or source.structure != target.structure:
                continue

            source_terms = keywords(text)
            target_terms = keywords(problem)
            surface = len(source_terms & target_terms) / max(
                1, len(source_terms | target_terms)
            )

            out.append(
                {
                    "structure": target.structure,
                    "source": text[:200],
                    "strategy": record.get("strategy", ""),
                    "succeeded": bool(record.get("success")),
                    "confidence": round((source.confidence + target.confidence) / 2, 4),
                    "surface_similarity": round(surface, 4),
                    "cross_domain": surface < 0.3,
                    "transferred_remedy": STRUCTURES[target.structure]["remedy"],
                }
            )

        # Prefer successful precedents, then structurally clean transfers.
        out.sort(
            key=lambda r: (r["succeeded"], r["confidence"], -r["surface_similarity"]),
            reverse=True,
        )

        return out[: int(limit)]

    # -------------------------------------------------------- transfer

    def transfer_strategy(
        self, strategy_steps: list[str], source_domain: str, target_domain: str
    ) -> dict[str, Any]:
        """Adapt a procedure across domains (section 22).

        Domain-specific nouns are marked as needing substitution rather than
        silently carried over, which is how a procedure gets adapted instead of
        misapplied.
        """

        vocabulary = {
            "coding": ["test", "build", "commit", "branch", "compile", "lint", "deploy"],
            "automation": ["window", "click", "app", "process", "file", "folder"],
            "research": ["source", "citation", "paper", "evidence", "claim"],
            "planning": ["milestone", "deadline", "schedule", "task"],
            "troubleshooting": ["symptom", "log", "error", "trace", "repro"],
        }

        source_words = {stem(w) for w in vocabulary.get(source_domain, [])}
        target_words = vocabulary.get(target_domain, [])

        adapted: list[str] = []
        substitutions: list[dict[str, str]] = []

        for step in strategy_steps:
            terms = keywords(step)
            domain_specific = terms & source_words

            if domain_specific:
                adapted.append(step)

                for term in sorted(domain_specific):
                    substitutions.append(
                        {
                            "step": step,
                            "term": term,
                            "needs": (
                                f"replace '{term}' with the {target_domain} equivalent"
                                + (f" (e.g. {target_words[0]})" if target_words else "")
                            ),
                        }
                    )

            else:
                adapted.append(step)

        return {
            "source_domain": source_domain,
            "target_domain": target_domain,
            "adapted_steps": adapted,
            "substitutions_required": substitutions,
            "transferable": len(substitutions) < len(strategy_steps),
            "confidence": round(
                max(0.2, 1.0 - len(substitutions) / max(1, len(strategy_steps))), 4
            ),
            "note": (
                "every step is domain-specific; this procedure does not transfer "
                "without redesign"
                if len(substitutions) >= len(strategy_steps)
                else "the general shape transfers; the marked terms need substitution"
            ),
        }

    # -------------------------------------------------------- counterfactual

    def counterfactual(
        self,
        state: dict[str, Any],
        change: dict[str, Any],
        rules: list[dict[str, Any]] | None = None,
        world_model: Any = None,
    ) -> dict[str, Any]:
        """Simulate "what would happen if" without executing (section 13).

        Runs entirely on a copy of the state. Consequences come from explicit
        rules and from real dependency relations in the world model, and
        anything the simulation cannot determine is reported as unknown rather
        than assumed benign.
        """

        actual = copy.deepcopy(dict(state))
        hypothetical = copy.deepcopy(actual)
        hypothetical.update(copy.deepcopy(dict(change)))

        effects: list[dict[str, Any]] = []
        unknowns: list[str] = []
        applied = True
        rounds = 0

        # Forward-chain the rules so second-order consequences appear.
        while applied and rounds < 5:
            applied = False
            rounds += 1

            for rule in rules or []:
                condition = rule.get("if", {})

                if not condition:
                    continue

                if all(hypothetical.get(k) == v for k, v in condition.items()):
                    outcome = rule.get("then", {})

                    if any(hypothetical.get(k) != v for k, v in outcome.items()):
                        hypothetical.update(outcome)
                        effects.append(
                            {
                                "cause": condition,
                                "effect": outcome,
                                "description": rule.get("description", ""),
                                "order": rounds,
                                "certainty": rule.get("certainty", "rule-based"),
                            }
                        )
                        applied = True

        # Dependency consequences from the real world model.
        if world_model is not None:
            for key in change:
                try:
                    dependents = world_model.depends_on(key)

                except Exception:
                    dependents = []

                for dependent in dependents:
                    effects.append(
                        {
                            "cause": {key: change[key]},
                            "effect": {dependent: "affected"},
                            "description": (
                                f"{dependent} depends on {key} and would be affected"
                            ),
                            "order": 1,
                            "certainty": "dependency-derived",
                        }
                    )

        for key in change:
            if not any(key in str(e.get("cause", "")) for e in effects):
                unknowns.append(
                    f"no rule or known dependency describes what changing "
                    f"'{key}' would affect - the consequence is unknown, not safe"
                )

        reversible = all(
            key in actual for key in change
        )

        return {
            "executed": False,
            "actual": actual,
            "hypothetical": hypothetical,
            "change": dict(change),
            "effects": effects,
            "unknowns": unknowns,
            "reversible": reversible,
            "confidence": round(
                max(0.1, 1.0 - 0.25 * len(unknowns)), 4
            ),
            "note": (
                "this is a simulation over a copied state; nothing was executed"
            ),
        }


transfer = TransferEngine()
