"""
==========================================
JARVIS PRO
AGI general problem solver
==========================================

Roadmap sections 7 (general problem solving), 16 (goal-directed behaviour),
17 (open-ended problem solving), 18 (novel-problem handling), 19 (unknown-task
understanding) and 21 (few-shot / zero-shot).

The design constraint is section 78: a problem must not be handled by matching
its command name. Understanding here works from the *shape* of the request -
what is being asked for, what is known, what is missing, what constrains it -
so a phrasing never seen before still decomposes.

An unknown problem is a first-class object, not a failure. :class:`Problem`
carries ``familiarity``, and an unfamiliar one routes into the open-ended loop
(understand -> search -> hypothesise -> experiment -> learn -> form skill)
rather than returning "I don't know how to do that".

    from agi.problem_solver import solver

    problem = solver.understand("get my downloads folder under control")
    problem.familiarity          # "novel"
    solver.decompose(problem)
"""

from __future__ import annotations

import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from .capabilities import capabilities
from .skill_library import skills
from .strategies import any_of, keywords, strategies
from .transfer import transfer
from .uncertainty import Belief, Evidence, ambiguous

KNOWN = "known"
PARTIAL = "partially-known"
NOVEL = "novel"

# Goal-shaped requests state an outcome; command-shaped ones state an action.
OUTCOME_MARKERS = (
    "ready", "working", "clean", "organised", "organized", "fixed", "faster",
    "better", "safe", "consistent", "up to date", "under control", "sorted",
    "reliable", "stable", "complete", "done", "tidy",
)

# Words that signal the request is under-specified.
VAGUE_MARKERS = (
    "better", "good", "nice", "proper", "somehow", "stuff", "things",
    "whatever", "etc", "and so on", "some", "a few", "improve", "optimise",
    "optimize", "clean up", "sort out",
)

CONSTRAINT_PATTERNS: list[tuple[str, re.Pattern]] = [
    # Built with any_of so inflected forms are caught. Written as
    # r"\b(quick|urgent)\b" these missed "quickly" and "urgently" - the single
    # most common way a user actually states a time constraint.
    ("time", re.compile(
        any_of("quick", "fast", "urgent", "rapid", "immediate", "soon", "today",
               "tonight", "deadline", "asap", "hurry")
        + r"|\bby \w+day\b|\bin \d+ (?:minute|hour|day)s?\b"
        # "before \w+" was too loose - it matched "before you change anything"
        # as a deadline. A time constraint needs an actual time reference.
        r"|\bbefore (?:\d|noon|midnight|monday|tuesday|wednesday|thursday|"
        r"friday|saturday|sunday|tomorrow|tonight|the (?:end|deadline))",
        re.I)),
    ("safety", re.compile(
        r"\b(?:without break\w*|don'?t break|do not break|without losing|"
        r"non-destructive|keep\w* (?:it )?working)\b|"
        + any_of("safely", "careful", "cautious"),
        re.I)),
    ("privacy", re.compile(
        any_of("private", "confidential", "personal", "local", "offline")
        + r"|\bdon'?t share\b|\bno cloud\b",
        re.I)),
    ("network", re.compile(
        r"\bno internet\b|\bwithout network\b|\blocal only\b|"
        + any_of("offline"),
        re.I)),
    ("budget", re.compile(
        any_of("free", "cheap", "budget", "inexpensive")
        + r"|\bno cost\b|\bunder \$?\d+\b",
        re.I)),
    ("permission", re.compile(
        r"\bask me\b|\bcheck with me\b|"
        + any_of("confirm", "approval", "approve", "permission"),
        re.I)),
    ("preference", re.compile(
        r"\binstead of\b|" + any_of("prefer", "rather"),
        re.I)),
]

# Multiple objectives joined by a tension word (section 35).
TENSION = re.compile(
    r"\b(but|however|while|without|although|yet|whilst)\b", re.IGNORECASE
)


@dataclass
class Problem:
    """A request reduced to the parts a planner needs."""

    request: str
    objective: str
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    domain: str = "general"
    known: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    constraints: list[dict[str, str]] = field(default_factory=list)
    resources: list[str] = field(default_factory=list)
    objectives: list[str] = field(default_factory=list)
    structures: list[dict[str, Any]] = field(default_factory=list)
    familiarity: str = NOVEL
    goal_shaped: bool = False
    ambiguous: bool = False
    ambiguity_question: str = ""
    entities: list[str] = field(default_factory=list)
    understanding: Belief = field(default_factory=lambda: Belief(True, 0.5))
    created: float = field(default_factory=time.time)

    @property
    def confidence(self) -> float:
        return self.understanding.confidence

    def ready_to_plan(self) -> bool:
        """Enough is understood to build a plan without guessing."""

        return not self.ambiguous and self.confidence >= 0.45 and bool(self.objective)

    def report(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "request": self.request,
            "objective": self.objective,
            "domain": self.domain,
            "known": list(self.known),
            "missing": list(self.missing),
            "constraints": list(self.constraints),
            "resources": list(self.resources),
            "objectives": list(self.objectives),
            "structures": list(self.structures),
            "familiarity": self.familiarity,
            "goal_shaped": self.goal_shaped,
            "ambiguous": self.ambiguous,
            "ambiguity_question": self.ambiguity_question,
            "entities": list(self.entities),
            "confidence": self.confidence,
            "ready_to_plan": self.ready_to_plan(),
            "created": self.created,
        }


@dataclass
class SubProblem:
    description: str
    verification: str
    depends_on: list[int] = field(default_factory=list)
    capability: str = ""
    gap: bool = False
    index: int = 0

    def report(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "description": self.description,
            "verification": self.verification,
            "depends_on": list(self.depends_on),
            "capability": self.capability,
            "gap": self.gap,
        }


DOMAIN_SIGNALS: dict[str, tuple[str, ...]] = {
    "coding": ("code", "python", "bug", "test", "function", "repo", "compile",
               "script", "import", "syntax", "refactor", "build", "commit"),
    "troubleshooting": ("slow", "crash", "fail", "error", "broken", "stuck",
                        "hang", "wrong", "unexpected", "diagnose", "why"),
    "automation": ("open", "launch", "click", "window", "app", "automate",
                   "file", "folder", "download", "rename", "organise", "organize"),
    "research": ("research", "find out", "source", "evidence", "compare",
                 "learn about", "explain", "what is", "investigate"),
    "planning": ("plan", "schedule", "goal", "milestone", "roadmap", "organise",
                 "prioritise", "prioritize", "deadline"),
    "business": ("cost", "customer", "revenue", "client", "invoice", "sales"),
}


class ProblemSolver:
    """Understands, decomposes and routes problems, familiar or not."""

    # ------------------------------------------------------------ understand

    def domain_of(self, text: str) -> tuple[str, float]:
        """Classify by weighted signal count, with a real confidence."""

        lowered = str(text).lower()
        terms = keywords(lowered)
        scores: dict[str, float] = {}

        for domain, signals in DOMAIN_SIGNALS.items():
            hits = 0.0

            for signal in signals:
                if " " in signal:
                    if signal in lowered:
                        hits += 1.5

                elif signal in terms:
                    hits += 1.0

            if hits:
                scores[domain] = hits

        if not scores:
            return "general", 0.3

        total = sum(scores.values())
        best = max(scores, key=scores.get)
        share = scores[best] / total

        # If two domains are close, the classification is weak - say so.
        if ambiguous({k: v / total for k, v in scores.items()}, margin=0.12):
            return best, round(share * 0.7, 4)

        return best, round(min(0.9, share), 4)

    def understand(self, request: str, context: dict[str, Any] | None = None) -> Problem:
        """Section 19: interpret a request without needing a trigger phrase."""

        text = str(request or "").strip()
        context = dict(context or {})
        lowered = text.lower()
        terms = keywords(text)

        domain, domain_confidence = self.domain_of(text)

        # Objective: what state should hold when this is done.
        goal_shaped = any(marker in lowered for marker in OUTCOME_MARKERS)
        objective = self._objective(text, goal_shaped)

        # Constraints hidden in the phrasing (section 19, 36).
        constraints: list[dict[str, str]] = []

        for kind, pattern in CONSTRAINT_PATTERNS:
            match = pattern.search(text)

            if match:
                constraints.append({"kind": kind, "phrase": match.group(0).strip()})

        # Multiple objectives in tension (section 35).
        objectives: list[str] = []

        if TENSION.search(text):
            parts = TENSION.split(text)
            objectives = [
                p.strip(" ,.") for p in parts
                if p.strip(" ,.") and p.strip().lower() not in
                {"but", "however", "while", "without", "although", "yet", "whilst"}
            ][:3]

        # What is stated vs what is needed but absent.
        entities = self._entities(text, context)
        known = [f"the request itself: {text[:120]}"]

        if entities:
            known.append("named entities: " + ", ".join(entities[:5]))

        if context.get("world"):
            known.append("current world state is available")

        missing = self._missing(text, entities, goal_shaped, context)

        # Ambiguity: vague wording, or no concrete referent for a concrete verb.
        vague = [marker for marker in VAGUE_MARKERS if marker in lowered]
        is_ambiguous = bool(vague) and not entities
        question = ""

        if is_ambiguous:
            question = self._question(text, vague)

        # Familiarity: does anything in the system already handle this?
        matching_skills = skills.find(text, limit=2)
        gap = capabilities.gaps(text)

        if matching_skills:
            familiarity = KNOWN

        elif not gap.get("gap"):
            familiarity = PARTIAL

        else:
            familiarity = NOVEL

        structures = transfer.structures_for(text)

        # Understanding confidence, built from real signals.
        understanding = Belief(True, 0.5, source="intent-analysis")
        understanding.support(
            Evidence("domain classification", True, domain_confidence)
        )

        if objective:
            understanding.support(Evidence("objective extracted", True, 0.6))

        if entities:
            understanding.support(Evidence("concrete referents present", True, 0.55))

        if matching_skills:
            understanding.support(
                Evidence("a verified skill matches this request", True, 0.7, verified=True)
            )

        if len(terms) < 2:
            understanding.refute(Evidence("request is very short", False, 0.5))

        for item in missing:
            understanding.assume(f"unstated: {item}")

        if is_ambiguous:
            understanding.refute(
                Evidence(f"vague wording: {', '.join(vague[:2])}", False, 0.6)
            )

        return Problem(
            request=text,
            objective=objective,
            domain=domain,
            known=known,
            missing=missing,
            constraints=constraints,
            resources=[c["capability"] for c in gap.get("candidates", [])[:4]],
            objectives=objectives,
            structures=structures[:3],
            familiarity=familiarity,
            goal_shaped=goal_shaped,
            ambiguous=is_ambiguous,
            ambiguity_question=question,
            entities=entities,
            understanding=understanding,
        )

    def _objective(self, text: str, goal_shaped: bool) -> str:
        """State the finished condition, not the action."""

        cleaned = re.sub(
            r"^\s*(please\s+|jarvis[,\s]+|can you\s+|could you\s+|i want you to\s+|"
            r"i need you to\s+|help me\s+)",
            "",
            str(text).strip(),
            flags=re.IGNORECASE,
        ).strip()

        if not cleaned:
            return ""

        if goal_shaped:
            return f"the state where: {cleaned.rstrip('.?!')}"

        return cleaned.rstrip(".?!")

    def _entities(self, text: str, context: dict[str, Any]) -> list[str]:
        found: list[str] = []

        found.extend(re.findall(r"[A-Za-z]:\\[^\s\"'<>|]+", text))
        found.extend(re.findall(r"(?:^|\s)(/[\w./-]+)", text))
        found.extend(
            re.findall(r"\b[\w-]+\.(?:py|md|txt|json|csv|pdf|docx|xlsx|zip|log|html|js)\b", text)
        )
        found.extend(re.findall(r"https?://[^\s]+", text))
        found.extend(re.findall(r"[\"']([^\"']{2,40})[\"']", text))
        found.extend(
            re.findall(
                r"\b(chrome|firefox|vscode|vs code|notepad|excel|word|whatsapp|"
                r"spotify|github|terminal|explorer|outlook)\b",
                text,
                re.IGNORECASE,
            )
        )
        found.extend(
            re.findall(r"\b(downloads?|documents?|desktop|pictures?|videos?)\b", text, re.I)
        )

        for item in context.get("entities", []) or []:
            found.append(str(item))

        out: list[str] = []

        for item in found:
            cleaned = str(item).strip()

            if cleaned and cleaned.lower() not in {x.lower() for x in out}:
                out.append(cleaned)

        return out[:12]

    def _missing(
        self,
        text: str,
        entities: list[str],
        goal_shaped: bool,
        context: dict[str, Any],
    ) -> list[str]:
        """What would have to be established before this can be planned."""

        lowered = str(text).lower()
        missing: list[str] = []

        if goal_shaped:
            missing.append("the checkable criteria that define 'done'")

        if not entities and re.search(
            r"\b(this|that|these|those|it|them|the file|the folder|the app)\b", lowered
        ):
            missing.append("which specific item the request refers to")

        if re.search(r"\b(organis|organiz|sort|clean|tidy|arrange)\w*\b", lowered):
            if not re.search(r"\bby\b|\baccording to\b|\binto\b", lowered):
                missing.append("the policy by which things should be arranged")

        if re.search(r"\b(all|every|each)\b", lowered) and not entities:
            missing.append("the scope that 'all' covers")

        if re.search(r"\b(fix|repair|solve)\b", lowered) and not re.search(
            r"\b(error|because|when|fail)\w*\b", lowered
        ):
            missing.append("the observed symptom to diagnose against")

        if "current_state" not in context and goal_shaped:
            missing.append("the current state to compare the target against")

        return missing[:5]

    def _question(self, text: str, vague: list[str]) -> str:
        """One specific question that resolves the ambiguity (section 63)."""

        lowered = str(text).lower()

        if re.search(r"\b(organis|organiz|sort|tidy|clean)\w*\b", lowered):
            return "By what should these be arranged - type, date, project, or something else?"

        if "better" in vague or "improve" in vague:
            return "What specifically should be better - speed, reliability, readability, or cost?"

        if re.search(r"\b(this|that|it|them)\b", lowered):
            return "Which item does this refer to?"

        return (
            f"This could be read more than one way because of '{vague[0]}'. "
            f"What outcome would count as done?"
        )

    # ------------------------------------------------------------ decompose

    def decompose(self, problem: Problem, max_parts: int = 8) -> list[SubProblem]:
        """Split into independently verifiable parts (section 7).

        Parts come from the problem's own structure and missing information,
        not from a fixed template keyed on a command name.
        """

        parts: list[SubProblem] = []

        def add(description: str, verification: str, depends: list[int] | None = None) -> None:
            if len(parts) >= max_parts:
                return

            index = len(parts)
            gap_report = capabilities.gaps(description)
            parts.append(
                SubProblem(
                    description=description,
                    verification=verification,
                    depends_on=list(depends or []),
                    capability="" if gap_report.get("gap") else gap_report.get("best", ""),
                    gap=bool(gap_report.get("gap")),
                    index=index,
                )
            )

        # 1. Resolve anything that would otherwise be guessed.
        for item in problem.missing:
            add(
                f"establish {item}",
                f"'{item}' is stated explicitly rather than assumed",
            )

        # 2. Observe the current state before changing it.
        if problem.goal_shaped or problem.entities:
            add(
                "observe the current state of "
                + (", ".join(problem.entities[:3]) if problem.entities else "the target"),
                "the observation is recorded in the world model with a timestamp",
                depends=[i for i in range(len(parts))],
            )

        observation_index = len(parts) - 1 if parts else None

        # 3. Structural checks implied by the problem's shape.
        for structure in problem.structures[:2]:
            add(
                structure["check"],
                f"the answer to '{structure['check']}' is recorded",
                depends=[observation_index] if observation_index is not None else [],
            )

        # 4. The substantive work.
        add(
            f"carry out: {problem.objective}",
            (
                "the checkable criteria are met"
                if problem.goal_shaped
                else f"the requested outcome is observable: {problem.objective[:80]}"
            ),
            depends=list(range(len(parts))),
        )

        # 5. Verification as an explicit step, never implicit.
        add(
            "verify the outcome independently of the action's return value",
            "an observation, not a return code, confirms the effect",
            depends=[len(parts) - 1],
        )

        return parts

    # ------------------------------------------------------------ open-ended

    def open_ended_plan(self, problem: Problem) -> dict[str, Any]:
        """Section 17/18: the loop for a problem with no existing skill.

        Produces a concrete, ordered investigation plan tied to this specific
        problem - the structures it matches, the capabilities that exist, the
        information it lacks.
        """

        from .hypotheses import hypotheses as hypothesis_engine

        steps: list[dict[str, Any]] = []

        steps.append(
            {
                "stage": "classify",
                "action": f"the problem reduces to: "
                          + (
                              ", ".join(s["structure"] for s in problem.structures)
                              or "no recognised structure"
                          ),
                "why": "a structural label makes past lessons retrievable",
            }
        )

        gap = capabilities.gaps(problem.request)
        steps.append(
            {
                "stage": "capability_check",
                "action": gap.get("reason", ""),
                "why": "an action cannot be planned onto a capability that is absent",
                "gap": gap.get("gap"),
                "next": gap.get("next", ""),
            }
        )

        # Retrieve analogous precedent from real experience.
        precedents: list[dict[str, Any]] = []

        try:
            from memory.experience import experience

            precedents = transfer.find_analogies(
                problem.request, experience.recent(limit=120), limit=3
            )

        except Exception:
            precedents = []

        steps.append(
            {
                "stage": "retrieve",
                "action": (
                    f"found {len(precedents)} structurally analogous precedent(s)"
                    if precedents
                    else "no structurally analogous precedent in experience"
                ),
                "why": "a solved problem with the same structure supplies a remedy",
                "precedents": precedents,
            }
        )

        # Generate real hypotheses about why this is hard, and register them.
        created: list[str] = []

        for structure in problem.structures[:2]:
            statement = (
                f"this problem is an instance of {structure['structure']}: "
                f"{structure['general']}"
            )
            h = hypothesis_engine.create(
                statement,
                prior=min(0.7, structure["confidence"]),
                tests=[structure["check"]],
            )
            created.append(h.id)

        for item in problem.missing:
            h = hypothesis_engine.create(
                f"the task cannot be completed until {item} is established",
                prior=0.6,
                tests=[f"attempt to establish {item}"],
            )
            created.append(h.id)

        steps.append(
            {
                "stage": "hypothesise",
                "action": f"registered {len(created)} testable hypotheses",
                "why": "an unknown problem is narrowed by testing, not by guessing",
                "hypothesis_ids": created,
            }
        )

        steps.append(
            {
                "stage": "experiment",
                "action": "run the cheapest read-only test for each hypothesis first",
                "why": "information-gathering experiments carry no risk of damage",
            }
        )

        steps.append(
            {
                "stage": "form_skill",
                "action": (
                    f"if a procedure succeeds and verifies, register it as a skill "
                    f"named '{self._skill_name(problem)}'"
                ),
                "why": "an unknown problem solved once should be known next time",
            }
        )

        return {
            "problem_id": problem.id,
            "familiarity": problem.familiarity,
            "steps": steps,
            "hypotheses": created,
            "precedents": precedents,
            "blocked_on": (
                problem.ambiguity_question if problem.ambiguous else ""
            ),
            "proposed_skill_name": self._skill_name(problem),
        }

    def _skill_name(self, problem: Problem) -> str:
        terms = sorted(keywords(problem.objective or problem.request))[:3]

        return "-".join(terms) if terms else f"task-{problem.id[:6]}"

    # ------------------------------------------------------------ routing

    def route(self, problem: Problem) -> dict[str, Any]:
        """Decide how this problem should be handled, and say why."""

        if problem.ambiguous:
            return {
                "route": "ask_human",
                "reason": "the request is ambiguous and a guess could be wrong",
                "question": problem.ambiguity_question,
            }

        matching = skills.find(problem.request, limit=1)

        if matching:
            skill = matching[0]

            return {
                "route": "known_skill",
                "skill": skill.name,
                "confidence": skill.confidence,
                "reason": (
                    f"'{skill.name}' is a verified skill matching this request "
                    f"({skill.successes}/{skill.attempts} in the field)"
                ),
            }

        selection = strategies.select(
            problem.request,
            problem.domain,
            constraints=[c["kind"] for c in problem.constraints],
        )

        if selection["found"] and problem.familiarity != NOVEL:
            return {
                "route": "strategy",
                "strategy": selection["strategy"].name,
                "reason": selection["reason"],
                "considered": selection["considered"],
            }

        return {
            "route": "open_ended",
            "reason": (
                "no verified skill and no confidently matching strategy - "
                "this is handled as a novel problem"
            ),
            "fallback_strategy": (
                selection["strategy"].name if selection["found"] else ""
            ),
        }


solver = ProblemSolver()
