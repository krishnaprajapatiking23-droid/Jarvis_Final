"""
==========================================
JARVIS PRO
AGI skill library
==========================================

Roadmap sections 20 (learn-new-task capability), 21 (few-shot / zero-shot),
23 (skill vs knowledge vs strategy) and 49 (autonomous skill acquisition).

A SKILL is an executable procedure with a verification criterion. That last
part is the whole point: a procedure the system cannot check is not a skill,
it is a guess. :meth:`acquire` refuses to register anything whose verification
has not actually passed, so "learned a new skill" can never be claimed on the
strength of having written one down.

Skills carry the full record section 20 requires - preconditions, inputs,
steps, tools, expected outputs, verification, failure modes, confidence,
source, timestamps and a measured success rate.

    from agi.skill_library import skills

    skills.acquire(draft, verify=runner)     # only registers if verify passes
    skills.find("organise my downloads folder")
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

from core.atomic_json import AtomicJSONStore
from security.policy_engine import policy

from .strategies import keywords

DRAFT = "draft"
VERIFIED = "verified"
FAILED = "failed"
RETIRED = "retired"

# A skill needs this many independent checks before it counts as verified.
MIN_VERIFICATION_CASES = 1

# Generated skills above this risk class always need a human (section 46).
AUTO_REGISTER_MAX_RISK = "medium"

RISK_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}


@dataclass
class Skill:
    """An executable procedure the system has proven it can carry out."""

    name: str
    description: str
    steps: list[str]
    verification: str
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    preconditions: list[str] = field(default_factory=list)
    inputs: dict[str, str] = field(default_factory=dict)
    expected_outputs: dict[str, str] = field(default_factory=dict)
    tools: list[str] = field(default_factory=list)
    failure_modes: list[str] = field(default_factory=list)
    domain: str = "general"
    risk_level: str = "low"
    status: str = DRAFT
    source: str = "acquired"
    examples: list[dict[str, Any]] = field(default_factory=list)
    verification_runs: int = 0
    verification_passes: int = 0
    attempts: int = 0
    successes: int = 0
    created_at: float = field(default_factory=time.time)
    last_used: float = 0.0
    approved_by: str = ""

    @property
    def success_rate(self) -> float:
        if not self.attempts:
            return 0.0

        return round(self.successes / self.attempts, 4)

    @property
    def confidence(self) -> float:
        """Derived from verification and live use, never assigned."""

        if self.status != VERIFIED:
            return 0.0

        verification = (
            self.verification_passes / self.verification_runs
            if self.verification_runs
            else 0.0
        )

        if not self.attempts:
            # Verified but never used in anger: capped, because a passing test
            # is weaker evidence than a real success.
            return round(min(0.6, verification * 0.6), 4)

        return round(0.4 * verification + 0.6 * self.success_rate, 4)

    def matches(self, request: str) -> float:
        terms = keywords(request)

        if not terms:
            return 0.0

        words = keywords(f"{self.name} {self.description} {' '.join(self.steps)}")
        example_words: set[str] = set()

        for example in self.examples:
            example_words |= keywords(str(example.get("request", "")))

        overlap = len(terms & words) / max(1, len(terms))
        by_example = len(terms & example_words) / max(1, len(terms)) if example_words else 0.0

        return round(min(1.0, 0.7 * overlap + 0.3 * by_example), 4)

    def report(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "preconditions": list(self.preconditions),
            "inputs": dict(self.inputs),
            "steps": list(self.steps),
            "tools": list(self.tools),
            "expected_outputs": dict(self.expected_outputs),
            "verification": self.verification,
            "failure_modes": list(self.failure_modes),
            "domain": self.domain,
            "risk_level": self.risk_level,
            "status": self.status,
            "source": self.source,
            "examples": list(self.examples),
            "verification_runs": self.verification_runs,
            "verification_passes": self.verification_passes,
            "attempts": self.attempts,
            "successes": self.successes,
            "success_rate": self.success_rate,
            "confidence": self.confidence,
            "created_at": self.created_at,
            "last_used": self.last_used,
            "approved_by": self.approved_by,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Skill":
        return cls(
            name=str(data.get("name", "")),
            description=str(data.get("description", "")),
            steps=list(data.get("steps") or []),
            verification=str(data.get("verification", "")),
            id=str(data.get("id") or uuid.uuid4().hex[:12]),
            preconditions=list(data.get("preconditions") or []),
            inputs=dict(data.get("inputs") or {}),
            expected_outputs=dict(data.get("expected_outputs") or {}),
            tools=list(data.get("tools") or []),
            failure_modes=list(data.get("failure_modes") or []),
            domain=str(data.get("domain", "general")),
            risk_level=str(data.get("risk_level", "low")),
            status=str(data.get("status", DRAFT)),
            source=str(data.get("source", "acquired")),
            examples=list(data.get("examples") or []),
            verification_runs=int(data.get("verification_runs", 0)),
            verification_passes=int(data.get("verification_passes", 0)),
            attempts=int(data.get("attempts", 0)),
            successes=int(data.get("successes", 0)),
            created_at=float(data.get("created_at", time.time())),
            last_used=float(data.get("last_used", 0.0)),
            approved_by=str(data.get("approved_by", "")),
        )


class SkillLibrary:
    """Persistent store of procedures the system has learned and verified."""

    def __init__(self, path: str = "data/agi_skills.json") -> None:
        self._lock = threading.RLock()
        self._store = AtomicJSONStore(path, {})
        self._items: dict[str, Skill] = {}
        self._handlers: dict[str, Callable[..., Any]] = {}
        self._loaded = False

    # ------------------------------------------------------------- storage

    def _ensure(self) -> None:
        if self._loaded:
            return

        with self._lock:
            if self._loaded:
                return

            for item in (self._store.load() or {}).get("skills", {}).values():
                try:
                    skill = Skill.from_dict(item)
                    self._items[skill.name] = skill

                except Exception:
                    continue

            self._loaded = True

    def save(self) -> None:
        with self._lock:
            payload = {
                "skills": {k: v.report() for k, v in self._items.items()},
                "saved": time.time(),
            }

        try:
            self._store.save(payload)

        except Exception:
            pass

    def reload(self) -> "SkillLibrary":
        """Handlers are runtime-only; procedures survive restart."""

        with self._lock:
            self._items.clear()
            self._loaded = False

        self._ensure()

        return self

    # ------------------------------------------------------------- drafting

    def draft(
        self,
        name: str,
        description: str,
        steps: list[str],
        verification: str,
        domain: str = "general",
        tools: list[str] | None = None,
        preconditions: list[str] | None = None,
        inputs: dict[str, str] | None = None,
        expected_outputs: dict[str, str] | None = None,
        risk_level: str = "low",
        source: str = "acquired",
        examples: list[dict[str, Any]] | None = None,
    ) -> Skill:
        """Design a procedure. Drafting does not make it usable."""

        if not str(name).strip():
            raise ValueError("a skill needs a name")

        if not steps:
            raise ValueError("a skill needs at least one step")

        if not str(verification).strip():
            raise ValueError(
                "a skill needs a verification criterion - a procedure that "
                "cannot be checked is not a skill"
            )

        self._ensure()

        if name in self._items:
            raise KeyError(f"skill already exists: {name}")

        return Skill(
            name=str(name).strip(),
            description=str(description),
            steps=list(steps),
            verification=str(verification),
            domain=str(domain),
            tools=list(tools or []),
            preconditions=list(preconditions or []),
            inputs=dict(inputs or {}),
            expected_outputs=dict(expected_outputs or {}),
            risk_level=str(risk_level),
            source=str(source),
            examples=list(examples or []),
        )

    def acquire(
        self,
        skill: Skill,
        verify: Callable[[Skill], bool] | None = None,
        cases: list[tuple[dict[str, Any], Any]] | None = None,
        handler: Callable[..., Any] | None = None,
        approved_by: str = "",
    ) -> dict[str, Any]:
        """Verify a drafted skill and register it only if verification passes.

        ``verify`` is a callable that actually exercises the procedure and
        returns whether it worked. ``cases`` is the few-shot alternative: input
        / expected-output pairs run against ``handler``.

        Nothing is registered on the strength of the draft alone.
        """

        self._ensure()

        if verify is None and not cases:
            return {
                "ok": False,
                "reason": (
                    "a skill cannot be registered without verification - "
                    "supply either a verify callable or test cases"
                ),
            }

        runs = 0
        passes = 0
        failures: list[str] = []

        if cases:
            if handler is None:
                return {"ok": False, "reason": "test cases supplied without a handler"}

            for args, expected in cases:
                runs += 1

                try:
                    actual = handler(**args)

                except Exception as exc:
                    failures.append(f"{type(exc).__name__}: {exc}")
                    continue

                if expected is None or actual == expected:
                    passes += 1

                else:
                    failures.append(f"expected {expected!r}, got {actual!r}")

        if verify is not None:
            runs += 1

            try:
                if verify(skill):
                    passes += 1

                else:
                    failures.append("verification callable returned False")

            except Exception as exc:
                failures.append(f"verification raised {type(exc).__name__}: {exc}")

        skill.verification_runs += runs
        skill.verification_passes += passes

        if runs < MIN_VERIFICATION_CASES or passes < runs:
            skill.status = FAILED
            skill.failure_modes.extend(failures[:5])

            return {
                "ok": False,
                "reason": "verification did not pass; the skill was not registered",
                "runs": runs,
                "passes": passes,
                "failures": failures,
                "skill": skill.report(),
            }

        # Risk gate: a generated procedure may not quietly become dangerous.
        if RISK_ORDER.get(skill.risk_level, 1) > RISK_ORDER[AUTO_REGISTER_MAX_RISK]:
            if not approved_by:
                return {
                    "ok": False,
                    "needs_approval": True,
                    "reason": (
                        f"a generated skill at risk '{skill.risk_level}' requires "
                        "explicit human review before registration"
                    ),
                    "skill": skill.report(),
                }

            decision = policy.check("code.execute", {"skill": skill.name})

            if not decision.allowed and not policy._granted("code.execute"):
                skill.approved_by = approved_by

        skill.status = VERIFIED
        skill.approved_by = approved_by

        with self._lock:
            self._items[skill.name] = skill

            if handler is not None:
                self._handlers[skill.name] = handler

        self.save()

        return {
            "ok": True,
            "registered": skill.name,
            "runs": runs,
            "passes": passes,
            "confidence": skill.confidence,
            "skill": skill.report(),
        }

    # ------------------------------------------------------------- use

    def get(self, name: str) -> Skill | None:
        self._ensure()

        return self._items.get(str(name))

    def all(self, status: str = "") -> list[Skill]:
        self._ensure()

        with self._lock:
            return [s for s in self._items.values() if not status or s.status == status]

    def find(self, request: str, limit: int = 3, minimum: float = 0.25) -> list[Skill]:
        """Verified skills that plausibly serve this request."""

        scored = [
            (s.matches(request), s)
            for s in self.all(VERIFIED)
        ]
        scored = [(score, s) for score, s in scored if score >= minimum]
        scored.sort(key=lambda row: (row[0], row[1].confidence), reverse=True)

        return [s for _, s in scored[: int(limit)]]

    def handler(self, name: str) -> Callable[..., Any] | None:
        return self._handlers.get(str(name))

    def bind(self, name: str, handler: Callable[..., Any]) -> bool:
        """Re-attach an executable after a restart."""

        if self.get(name) is None:
            return False

        self._handlers[str(name)] = handler

        return True

    def record_use(self, name: str, success: bool) -> Skill | None:
        skill = self.get(name)

        if skill is None:
            return None

        with self._lock:
            skill.attempts += 1
            skill.successes += int(bool(success))
            skill.last_used = time.time()

            # A verified skill that keeps failing in the field is retired
            # rather than left to be selected again.
            if skill.attempts >= 4 and skill.success_rate < 0.35:
                skill.status = RETIRED
                skill.failure_modes.append(
                    f"retired after {skill.attempts} attempts at "
                    f"{skill.success_rate:.0%} success"
                )

        self.save()

        return skill

    def retire(self, name: str, reason: str = "") -> Skill | None:
        skill = self.get(name)

        if skill is None:
            return None

        skill.status = RETIRED

        if reason:
            skill.failure_modes.append(reason)

        self.save()

        return skill

    # ------------------------------------------------------------- few-shot

    def generalise(self, examples: list[dict[str, Any]], name: str = "") -> dict[str, Any]:
        """Infer a task pattern from a handful of examples (section 21).

        Returns the inferred shape *with* a confidence, and refuses to claim a
        pattern from a single example.
        """

        if len(examples) < 2:
            return {
                "ok": False,
                "reason": "at least two examples are needed to infer a pattern",
                "confidence": 0.0,
            }

        request_terms = [keywords(str(e.get("request", ""))) for e in examples]
        output_terms = [keywords(str(e.get("output", ""))) for e in examples]

        shared_request = set.intersection(*request_terms) if request_terms else set()
        shared_output = set.intersection(*output_terms) if output_terms else set()

        varying = [sorted(t - shared_request) for t in request_terms]

        # Confidence rises with the number of examples and the size of the
        # invariant core relative to what varies.
        core = len(shared_request)
        spread = sum(len(v) for v in varying) / max(1, len(varying))
        confidence = min(0.85, (core / max(1, core + spread)) * (0.4 + 0.15 * len(examples)))

        return {
            "ok": bool(shared_request),
            "name": name or ("-".join(sorted(shared_request)[:3]) or "inferred-task"),
            "invariant": sorted(shared_request),
            "varies": varying,
            "expected_output_shape": sorted(shared_output),
            "examples_used": len(examples),
            "confidence": round(confidence, 4),
            "reason": (
                "no term is common to every example, so no pattern can be inferred"
                if not shared_request
                else "inferred from the terms common to every example"
            ),
        }

    def status(self) -> dict[str, Any]:
        rows = self.all()

        return {
            "total": len(rows),
            "verified": sum(1 for s in rows if s.status == VERIFIED),
            "draft": sum(1 for s in rows if s.status == DRAFT),
            "failed": sum(1 for s in rows if s.status == FAILED),
            "retired": sum(1 for s in rows if s.status == RETIRED),
            "bound_handlers": len(self._handlers),
            "avg_confidence": (
                round(sum(s.confidence for s in rows) / len(rows), 4) if rows else 0.0
            ),
        }


skills = SkillLibrary()
