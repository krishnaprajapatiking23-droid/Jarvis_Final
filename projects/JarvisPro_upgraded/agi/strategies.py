"""
==========================================
JARVIS PRO
AGI strategy engine
==========================================

Roadmap sections 14 (strategic reasoning), 47 (novel strategy discovery),
72 (experience -> strategy pipeline), 73 (strategy selection) and
74 (strategy replacement).

The distinction this module exists to enforce (section 23):

* KNOWLEDGE is information.
* SKILL is an executable procedure.
* STRATEGY is a reusable *method for choosing* procedures.

A strategy is domain-tagged but not domain-bound: :meth:`select` deliberately
considers strategies proven in other domains at a discount rather than
excluding them, which is what makes cross-domain transfer possible (section 8).

Strategies are not written by hand only. :meth:`mine` reads the real
:mod:`memory.experience` store, finds patterns across repeated successes, and
proposes strategy candidates from them - the section 72 pipeline.

    from agi.strategies import strategies

    strategies.select("fix the failing build", domain="coding")
    strategies.record_outcome(name, success=True, duration=3.2)
"""

from __future__ import annotations

import re
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from core.atomic_json import AtomicJSONStore

STOP_WORDS = {
    "the", "a", "an", "my", "me", "i", "to", "of", "and", "on", "in", "for",
    "please", "jarvis", "can", "could", "would", "is", "it", "this", "that",
    "with", "from", "by", "at", "be", "was", "are",
}

# A strategy must fail this many times before replacement is considered.
FAILURE_PATIENCE = 3

# Below this success rate (with enough attempts) a strategy is deprecated.
POOR_PERFORMANCE = 0.4

# Cross-domain reuse penalty: a strategy proven elsewhere is worth trying but
# should not outrank one proven here.
TRANSFER_DISCOUNT = 0.75


# Suffixes stripped so "failing", "failed" and "fails" all reduce to "fail".
# Without this, pattern matching degrades into the exact-string matching that
# section 78 of the roadmap exists to eliminate.
SUFFIXES = ("ingly", "edly", "ing", "ies", "ied", "ed", "es", "s", "ly")


def stem(word: str) -> str:
    word = str(word).lower()

    for suffix in SUFFIXES:
        if len(word) > len(suffix) + 2 and word.endswith(suffix):
            trimmed = word[: -len(suffix)]

            # "ies" -> "y" (dependencies -> dependency)
            if suffix in ("ies", "ied"):
                return trimmed + "y"

            # Undo doubled consonants: "running" -> "runn" -> "run".
            # A doubled "s" is excluded because it is almost always part of the
            # root (miss, pass, process, address); stripping it turned
            # "missing" into "mis", which then falsely matched "miss".
            if (
                suffix in ("ing", "ed", "edly", "ingly")
                and len(trimmed) > 2
                and trimmed[-1] == trimmed[-2]
                and trimmed[-1] not in "aeious"
            ):
                trimmed = trimmed[:-1]

            return trimmed

    return word


# Compound identifiers carry the most diagnostic information in this domain -
# ModuleNotFoundError, FileNotFoundError, ConnectionRefusedError - but arrive
# as a single token, so signal matching missed them entirely. Splitting
# CamelCase and snake_case turns them back into readable words.
_CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")
_SEPARATORS = re.compile(r"[_\-./\\:]+")


def normalise(text: str) -> str:
    """Expand compound identifiers into space-separated words, lowercased.

    ``"ModuleNotFoundError"`` becomes ``"module not found error"``, so both
    single-word signals and multi-word phrases can match it.
    """

    expanded = _CAMEL.sub(" ", str(text or ""))
    expanded = _SEPARATORS.sub(" ", expanded)

    return re.sub(r"\s+", " ", expanded).strip().lower()


def keywords(text: str) -> set[str]:
    """Stemmed content words, used for structural rather than literal matching."""

    return {
        stem(w)
        for w in re.findall(r"[a-z0-9]+", normalise(text))
        if w not in STOP_WORDS and len(w) > 2
    }


@dataclass
class Strategy:
    """A reusable method for approaching a class of problem."""

    name: str
    steps: list[str]
    description: str = ""
    domains: list[str] = field(default_factory=list)
    problem_pattern: list[str] = field(default_factory=list)
    preconditions: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    failure_modes: list[str] = field(default_factory=list)
    fallback: str = ""
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    attempts: int = 0
    successes: int = 0
    total_duration: float = 0.0
    consecutive_failures: int = 0
    deprecated: bool = False
    replaced_by: str = ""
    source: str = "designed"
    created: float = field(default_factory=time.time)
    last_used: float = 0.0

    @property
    def success_rate(self) -> float:
        if not self.attempts:
            return 0.5  # untried: neither trusted nor condemned

        return round(self.successes / self.attempts, 4)

    @property
    def avg_duration(self) -> float:
        if not self.successes:
            return 0.0

        return round(self.total_duration / self.successes, 4)

    @property
    def proven(self) -> bool:
        return self.attempts >= 3 and self.success_rate >= 0.6

    def fits(self, problem: str, domain: str = "") -> float:
        """How well this strategy matches a problem, 0..1.

        Structural pattern match dominates surface wording, so a strategy
        learned as "retry after clearing the resource conflict" can match an
        unfamiliar phrasing of the same shape.
        """

        terms = keywords(problem)

        if not terms:
            return 0.0

        pattern = set()

        for item in self.problem_pattern:
            pattern |= keywords(item)

        surface = keywords(self.name + " " + self.description)

        matched = terms & pattern

        # Coverage: how much of the problem this pattern accounts for.
        coverage = len(matched) / max(1, len(terms)) if pattern else 0.0

        # Precision: how much of the pattern the problem hit. Kept as a smaller
        # term so a broad, well-tested pattern is not punished for being broad.
        precision = len(matched) / max(1, len(pattern)) if pattern else 0.0

        surface_score = len(terms & surface) / max(1, len(terms))

        score = 0.55 * coverage + 0.2 * precision + 0.25 * surface_score

        if domain:
            if domain in self.domains:
                score *= 1.0

            elif self.domains:
                score *= TRANSFER_DISCOUNT

        return round(min(1.0, score), 4)

    def report(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "steps": list(self.steps),
            "domains": list(self.domains),
            "problem_pattern": list(self.problem_pattern),
            "preconditions": list(self.preconditions),
            "constraints": list(self.constraints),
            "failure_modes": list(self.failure_modes),
            "fallback": self.fallback,
            "attempts": self.attempts,
            "successes": self.successes,
            "success_rate": self.success_rate,
            "avg_duration": self.avg_duration,
            "consecutive_failures": self.consecutive_failures,
            "deprecated": self.deprecated,
            "replaced_by": self.replaced_by,
            "proven": self.proven,
            "source": self.source,
            "created": self.created,
            "last_used": self.last_used,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Strategy":
        return cls(
            name=str(data.get("name", "")),
            steps=list(data.get("steps") or []),
            description=str(data.get("description", "")),
            domains=list(data.get("domains") or []),
            problem_pattern=list(data.get("problem_pattern") or []),
            preconditions=list(data.get("preconditions") or []),
            constraints=list(data.get("constraints") or []),
            failure_modes=list(data.get("failure_modes") or []),
            fallback=str(data.get("fallback", "")),
            id=str(data.get("id") or uuid.uuid4().hex[:12]),
            attempts=int(data.get("attempts", 0)),
            successes=int(data.get("successes", 0)),
            total_duration=float(data.get("total_duration", 0.0)),
            consecutive_failures=int(data.get("consecutive_failures", 0)),
            deprecated=bool(data.get("deprecated", False)),
            replaced_by=str(data.get("replaced_by", "")),
            source=str(data.get("source", "designed")),
            created=float(data.get("created", time.time())),
            last_used=float(data.get("last_used", 0.0)),
        )


# Seed strategies. These are genuine general methods, not answers - each is a
# way of *choosing* what to do, and each still has to earn its success rate.
SEED_STRATEGIES: list[dict[str, Any]] = [
    {
        "name": "decompose-and-verify",
        "description": "split the goal into independently checkable parts and verify each",
        "steps": [
            "state the finished condition in checkable terms",
            "split into parts that can each be verified alone",
            "order the parts by dependency",
            "execute one part",
            "verify that part before starting the next",
            "stop and replan if a verification fails",
        ],
        "domains": ["general", "coding", "planning", "automation"],
        "problem_pattern": ["multi step", "build", "project", "organise", "release", "setup"],
        "failure_modes": ["a part cannot be verified independently"],
        "fallback": "hypothesis-first",
    },
    {
        "name": "hypothesis-first",
        "description": "generate candidate explanations and test the cheapest discriminating one",
        "steps": [
            "collect the observed symptoms",
            "generate candidate explanations",
            "rank by prior likelihood and cost to test",
            "run the cheapest test that separates the leaders",
            "update confidence from the result",
            "repeat until one explanation is supported",
        ],
        "domains": ["troubleshooting", "coding", "research", "general"],
        "problem_pattern": ["fail", "error", "broken", "crash", "slow", "unexpected", "why", "diagnose"],
        "failure_modes": ["no test distinguishes the candidates"],
        "fallback": "narrow-the-search-space",
    },
    {
        "name": "narrow-the-search-space",
        "description": "halve the space of possible causes with each observation",
        "steps": [
            "define the space of possible causes",
            "find an observation that splits it roughly in half",
            "make that observation",
            "discard the eliminated half",
            "repeat until one candidate remains",
        ],
        "domains": ["troubleshooting", "coding", "general"],
        "problem_pattern": ["somewhere", "intermittent", "which", "find", "locate", "conflict"],
        "failure_modes": ["the space cannot be partitioned cleanly"],
        "fallback": "gather-then-decide",
    },
    {
        "name": "gather-then-decide",
        "description": "refuse to act until the missing information is collected",
        "steps": [
            "list what is known",
            "list what is missing and would change the decision",
            "collect the missing information by the cheapest safe route",
            "re-evaluate whether the goal is still the right one",
            "decide",
        ],
        "domains": ["general", "research", "planning", "business"],
        "problem_pattern": ["unclear", "unknown", "ambiguous", "decide", "compare", "choose", "should"],
        "failure_modes": ["the information is not obtainable"],
        "fallback": "ask-the-human",
    },
    {
        "name": "reversible-first",
        "description": "do the undoable part last and prove the reversible part works first",
        "steps": [
            "separate reversible steps from irreversible ones",
            "execute and verify every reversible step",
            "prepare a rollback for the irreversible step",
            "request approval for the irreversible step",
            "execute it only after approval",
            "verify and keep the rollback available",
        ],
        "domains": ["automation", "general", "coding"],
        "problem_pattern": ["delete", "remove", "overwrite", "migrate", "install", "clean", "reset"],
        "failure_modes": ["no rollback is possible"],
        "fallback": "ask-the-human",
    },
    {
        "name": "ask-the-human",
        "description": "stop and get the missing decision from the person",
        "steps": [
            "state precisely what is unknown or unsafe",
            "state what each option would do",
            "ask one specific question",
            "wait for the answer",
            "proceed under the answer",
        ],
        "domains": ["general"],
        "problem_pattern": ["permission", "risky", "unsure", "ambiguous", "credential", "external"],
        "failure_modes": ["the human is unavailable"],
        "fallback": "",
    },
    {
        "name": "adapt-known-procedure",
        "description": "take a procedure that worked on a structurally similar problem and adjust it",
        "steps": [
            "abstract the current problem to its structure",
            "find a past problem with the same structure",
            "list where the two differ",
            "adjust the procedure for each difference",
            "run it on the smallest possible case first",
            "verify, then apply fully",
        ],
        "domains": ["general", "coding", "automation", "research"],
        "problem_pattern": ["similar", "like", "again", "another", "same", "new", "unfamiliar"],
        "failure_modes": ["the structural match was superficial"],
        "fallback": "gather-then-decide",
    },
]


class StrategyRegistry:
    """Persistent registry with selection, outcome tracking and replacement."""

    def __init__(self, path: str = "data/agi_strategies.json") -> None:
        self._lock = threading.RLock()
        self._store = AtomicJSONStore(path, {})
        self._items: dict[str, Strategy] = {}
        self._decisions: list[dict[str, Any]] = []
        self._loaded = False

    # ------------------------------------------------------------- storage

    def _ensure(self) -> None:
        if self._loaded:
            return

        with self._lock:
            if self._loaded:
                return

            data = self._store.load() or {}

            for item in (data.get("strategies") or {}).values():
                try:
                    s = Strategy.from_dict(item)
                    self._items[s.name] = s

                except Exception:
                    continue

            self._decisions = [
                d for d in (data.get("decisions") or []) if isinstance(d, dict)
            ]
            self._loaded = True

            if not self._items:
                for spec in SEED_STRATEGIES:
                    strategy = Strategy(source="seed", **spec)
                    self._items[strategy.name] = strategy

        self.save()

    def save(self) -> None:
        with self._lock:
            payload = {
                "strategies": {k: v.report() for k, v in self._items.items()},
                "decisions": self._decisions[-200:],
                "saved": time.time(),
            }

        try:
            self._store.save(payload)

        except Exception:
            pass

    def reload(self) -> "StrategyRegistry":
        with self._lock:
            self._items.clear()
            self._decisions.clear()
            self._loaded = False

        self._ensure()

        return self

    # ------------------------------------------------------------- CRUD

    def register(self, strategy: Strategy) -> Strategy:
        self._ensure()

        with self._lock:
            if strategy.name in self._items:
                raise KeyError(f"strategy already registered: {strategy.name}")

            self._items[strategy.name] = strategy

        self.save()

        return strategy

    def add(self, name: str, steps: list[str], **meta: Any) -> Strategy:
        return self.register(Strategy(name=str(name), steps=list(steps), **meta))

    def get(self, name: str) -> Strategy | None:
        self._ensure()

        return self._items.get(str(name))

    def all(self, include_deprecated: bool = False) -> list[Strategy]:
        self._ensure()

        with self._lock:
            return [
                s for s in self._items.values()
                if include_deprecated or not s.deprecated
            ]

    # ------------------------------------------------------------- selection

    def candidates(
        self, problem: str, domain: str = "", limit: int = 5
    ) -> list[tuple[Strategy, float, str]]:
        """Scored candidates with the reason each scored as it did."""

        out: list[tuple[Strategy, float, str]] = []

        for strategy in self.all():
            fit = strategy.fits(problem, domain)

            if fit <= 0:
                continue

            # History matters, but an untried strategy is not punished to zero.
            history = strategy.success_rate
            recency = 0.05 if strategy.last_used and (time.time() - strategy.last_used) < 86400 else 0.0
            penalty = 0.15 * min(3, strategy.consecutive_failures)

            score = round(0.55 * fit + 0.35 * history + recency - penalty, 4)

            reasons = [f"pattern fit {fit:.2f}"]

            if strategy.attempts:
                reasons.append(
                    f"{strategy.successes}/{strategy.attempts} past successes"
                )

            else:
                reasons.append("never tried")

            if domain and domain not in strategy.domains and strategy.domains:
                reasons.append(f"transferred from {', '.join(strategy.domains[:2])}")

            if strategy.consecutive_failures:
                reasons.append(f"{strategy.consecutive_failures} recent failures")

            out.append((strategy, max(0.0, score), "; ".join(reasons)))

        out.sort(key=lambda row: row[1], reverse=True)

        return out[: int(limit)]

    def select(
        self,
        problem: str,
        domain: str = "",
        exclude: list[str] | None = None,
        constraints: list[str] | None = None,
    ) -> dict[str, Any]:
        """Choose a strategy and record *why*, as section 73 requires."""

        excluded = {str(x) for x in (exclude or [])}
        blocked = {str(c).lower() for c in (constraints or [])}
        ranked = self.candidates(problem, domain, limit=8)

        considered = [
            {"name": s.name, "score": score, "reason": reason}
            for s, score, reason in ranked
        ]

        for strategy, score, reason in ranked:
            if strategy.name in excluded:
                continue

            # Respect goal constraints: a strategy whose own constraints clash
            # with the goal's is skipped rather than silently violating them.
            if blocked and any(c.lower() in blocked for c in strategy.constraints):
                continue

            decision = {
                "problem": str(problem)[:200],
                "domain": domain,
                "selected": strategy.name,
                "score": score,
                "reason": reason,
                "considered": considered,
                "at": time.time(),
            }

            with self._lock:
                self._decisions.append(decision)
                del self._decisions[:-200]

            self.save()

            return {
                "found": True,
                "strategy": strategy,
                "score": score,
                "reason": reason,
                "considered": considered,
            }

        return {
            "found": False,
            "strategy": None,
            "reason": "no registered strategy matches this problem",
            "considered": considered,
        }

    def why(self, limit: int = 10) -> list[dict[str, Any]]:
        """Recent selection decisions with their justifications."""

        self._ensure()

        with self._lock:
            return list(self._decisions[-int(limit):])[::-1]

    # ------------------------------------------------------------- outcomes

    def record_outcome(
        self, name: str, success: bool, duration: float = 0.0, note: str = ""
    ) -> Strategy | None:
        strategy = self.get(name)

        if strategy is None:
            return None

        with self._lock:
            strategy.attempts += 1
            strategy.last_used = time.time()

            if success:
                strategy.successes += 1
                strategy.total_duration += max(0.0, float(duration))
                strategy.consecutive_failures = 0

            else:
                strategy.consecutive_failures += 1

                if note and note not in strategy.failure_modes:
                    strategy.failure_modes.append(note)
                    del strategy.failure_modes[:-10]

        self.save()

        return strategy

    def failing(self) -> list[Strategy]:
        """Strategies performing badly enough to warrant replacement."""

        return [
            s
            for s in self.all()
            if s.consecutive_failures >= FAILURE_PATIENCE
            or (s.attempts >= 5 and s.success_rate < POOR_PERFORMANCE)
        ]

    def propose_replacement(self, name: str) -> dict[str, Any]:
        """Build a replacement for a failing strategy (section 74).

        The replacement is derived from the failing strategy's own recorded
        failure modes plus the best-performing strategy that shares a domain -
        not invented from nothing.
        """

        failing = self.get(name)

        if failing is None:
            return {"ok": False, "reason": "unknown strategy"}

        if failing.consecutive_failures < FAILURE_PATIENCE and failing.success_rate >= POOR_PERFORMANCE:
            return {
                "ok": False,
                "reason": "strategy has not failed often enough to replace",
                "consecutive_failures": failing.consecutive_failures,
            }

        siblings = [
            s
            for s in self.all()
            if s.name != name
            and s.proven
            and (set(s.domains) & set(failing.domains) or not failing.domains)
        ]
        donor = max(siblings, key=lambda s: s.success_rate, default=None)

        steps: list[str] = []

        # Start from what the failing strategy's failure modes say went wrong.
        for mode in failing.failure_modes[-3:]:
            steps.append(f"check first whether this applies: {mode}")

        if donor:
            steps.extend(donor.steps)
            origin = f"derived from {donor.name} ({donor.successes}/{donor.attempts})"

        else:
            steps.extend(failing.steps)
            steps.insert(0, "verify each precondition explicitly before acting")
            origin = "derived from the failing strategy with added precondition checks"

        candidate = Strategy(
            name=f"{failing.name}-v2",
            steps=steps,
            description=f"replacement for {failing.name}: {origin}",
            domains=list(failing.domains),
            problem_pattern=list(failing.problem_pattern),
            failure_modes=[],
            fallback=failing.fallback or (donor.name if donor else ""),
            source="replacement",
        )

        return {
            "ok": True,
            "candidate": candidate,
            "replacing": failing.name,
            "origin": origin,
            "evidence": {
                "consecutive_failures": failing.consecutive_failures,
                "success_rate": failing.success_rate,
                "attempts": failing.attempts,
                "failure_modes": list(failing.failure_modes),
            },
        }

    def adopt_replacement(
        self, name: str, candidate: Strategy, validated: bool
    ) -> dict[str, Any]:
        """Swap in a replacement only once it has outperformed the original."""

        failing = self.get(name)

        if failing is None:
            return {"ok": False, "reason": "unknown strategy"}

        if not validated:
            return {
                "ok": False,
                "reason": "replacement was not validated against the original",
            }

        with self._lock:
            if candidate.name not in self._items:
                self._items[candidate.name] = candidate

            failing.deprecated = True
            failing.replaced_by = candidate.name

        self.save()

        return {
            "ok": True,
            "adopted": candidate.name,
            "deprecated": failing.name,
            "rollback": (
                f"set deprecated=False on {failing.name} to restore it"
            ),
        }

    def rollback_replacement(self, name: str) -> bool:
        """Undo an adoption (section 44 requires a rollback path)."""

        strategy = self.get(name)

        if strategy is None or not strategy.deprecated:
            return False

        with self._lock:
            strategy.deprecated = False
            strategy.replaced_by = ""
            strategy.consecutive_failures = 0

        self.save()

        return True

    # ------------------------------------------------------------- mining

    def mine(self, minimum: int = 3, store: Any = None) -> list[dict[str, Any]]:
        """Extract strategy candidates from accumulated experience.

        This is the section 72 pipeline: many experiences -> similarity
        analysis -> pattern extraction -> candidate -> ranking. It reads the
        real :mod:`memory.experience` SQLite store.
        """

        if store is None:
            try:
                from memory.experience import experience as store

            except Exception:
                return []

        try:
            rows = store.recent(limit=300)

        except Exception:
            return []

        # Cluster successful attempts by the strategy that was used and the
        # vocabulary of the goals it worked on.
        clusters: dict[str, dict[str, Any]] = {}

        for row in rows:
            if not row.get("success"):
                continue

            name = str(row.get("strategy") or "").strip()

            if not name:
                continue

            bucket = clusters.setdefault(
                name,
                {"count": 0, "terms": {}, "durations": [], "goals": []},
            )
            bucket["count"] += 1
            bucket["durations"].append(float(row.get("duration") or 0.0))
            bucket["goals"].append(str(row.get("goal") or "")[:120])

            for term in keywords(row.get("goal") or ""):
                bucket["terms"][term] = bucket["terms"].get(term, 0) + 1

        candidates: list[dict[str, Any]] = []

        for name, bucket in clusters.items():
            if bucket["count"] < minimum:
                continue

            # Terms appearing in most of the cluster are the problem pattern.
            threshold = max(2, bucket["count"] // 2)
            pattern = sorted(
                [t for t, n in bucket["terms"].items() if n >= threshold]
            )

            if not pattern:
                continue

            existing = self.get(name)
            durations = [d for d in bucket["durations"] if d > 0]

            candidates.append(
                {
                    "name": name,
                    "occurrences": bucket["count"],
                    "problem_pattern": pattern[:12],
                    "avg_duration": round(sum(durations) / len(durations), 4) if durations else 0.0,
                    "examples": bucket["goals"][:3],
                    "already_registered": existing is not None,
                    "action": "extend existing pattern" if existing else "register new strategy",
                }
            )

        candidates.sort(key=lambda c: c["occurrences"], reverse=True)

        return candidates

    def absorb(self, candidates: list[dict[str, Any]] | None = None) -> list[str]:
        """Apply mined candidates: register new, widen the pattern of existing."""

        candidates = self.mine() if candidates is None else candidates
        changed: list[str] = []

        for candidate in candidates:
            name = candidate["name"]
            existing = self.get(name)

            if existing is None:
                self.add(
                    name,
                    steps=[f"apply the {name} approach"],
                    description=(
                        f"mined from {candidate['occurrences']} successful experiences"
                    ),
                    problem_pattern=candidate["problem_pattern"],
                    domains=["general"],
                    source="mined",
                )
                changed.append(f"registered {name}")

            else:
                before = set(existing.problem_pattern)
                merged = sorted(before | set(candidate["problem_pattern"]))

                if merged != sorted(before):
                    with self._lock:
                        existing.problem_pattern = merged[:20]

                    changed.append(f"widened {name}")

        if changed:
            self.save()

        return changed

    def status(self) -> dict[str, Any]:
        rows = self.all(include_deprecated=True)

        return {
            "total": len(rows),
            "active": sum(1 for s in rows if not s.deprecated),
            "deprecated": sum(1 for s in rows if s.deprecated),
            "proven": sum(1 for s in rows if s.proven),
            "failing": len(self.failing()),
            "mined": sum(1 for s in rows if s.source == "mined"),
            "decisions_recorded": len(self._decisions),
        }


strategies = StrategyRegistry()


# --------------------------------------------------------------------------
# Shared pattern builder.
#
# Hand-written alternations of the form r"\b(quick|urgent)\b" silently fail on
# every inflected form: "quickly", "urgently", "budgets", "permissions" all
# escape, because \b sits immediately after the stem. That single mistake
# produced three separate defects (a secrets boundary that missed "api keys",
# a constraint extractor that missed "quickly", and strategy matching that
# missed "failing"), so the tolerance is built into one helper rather than
# rediscovered per pattern.

INFLECTIONS = r"(?:s|es|ed|ing|ly|d)?"


def any_of(*words: str) -> str:
    """A word-boundary alternation that tolerates common inflected forms.

    Multi-word phrases are matched literally, since a suffix on a phrase would
    attach to its last word and rarely means anything useful.
    """

    single = [w for w in words if " " not in w]
    phrases = [w for w in words if " " in w]

    parts: list[str] = []

    if single:
        parts.append(r"\b(?:" + "|".join(single) + r")" + INFLECTIONS + r"\b")

    for phrase in phrases:
        parts.append(r"\b" + phrase + r"\b")

    return "(?:" + "|".join(parts) + ")"
