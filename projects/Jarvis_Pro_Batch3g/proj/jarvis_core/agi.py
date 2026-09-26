"""General-intelligence engine (Section 41).

These are practical engineering equivalents of the 29 requested reasoning
capabilities, not a claim of true AGI. Every capability returns a structured
``Reasoning`` record with input, reasoning process (steps), output, confidence
and evidence, so behaviour is measurable and testable.
"""

from __future__ import annotations

import json
import math
import os
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from jarvis_core.learning import LearningEngine, learning as default_learning, tokenize

__all__ = [
    "CAPABILITIES",
    "Reasoning",
    "WorldModel",
    "AGIEngine",
    "agi",
]

CAPABILITIES: Tuple[str, ...] = (
    "transfer_learning",
    "cross_domain_reasoning",
    "abstract_reasoning",
    "causal_reasoning",
    "common_sense_reasoning",
    "analogical_reasoning",
    "counterfactual_reasoning",
    "strategic_reasoning",
    "long_horizon_reasoning",
    "open_ended_problem_solving",
    "novel_problem_handling",
    "unknown_task_understanding",
    "learn_new_task",
    "cross_task_transfer",
    "knowledge_generalization",
    "skill_generalization",
    "strategy_generalization",
    "continual_adaptation",
    "self_directed_learning",
    "curiosity_exploration",
    "hypothesis_generation",
    "hypothesis_testing",
    "experiment_planning",
    "world_model_construction",
    "environment_modeling",
    "causal_world_understanding",
    "capability_expansion",
    "novel_strategy_discovery",
    "autonomous_knowledge_acquisition",
)

COMMON_SENSE_RULES: Tuple[Tuple[str, str, str], ...] = (
    ("delete", "irreversible", "deleting data cannot be undone without a backup"),
    ("shutdown", "disruptive", "shutting a machine down ends every running task"),
    ("send", "irreversible", "a sent message cannot be unsent"),
    ("payment", "irreversible", "money transfers are hard to reverse"),
    ("offline", "blocked", "network actions cannot succeed without connectivity"),
    ("password", "sensitive", "credentials must never be echoed or logged"),
    ("night", "timing", "loud or intrusive actions are unwelcome late at night"),
)


@dataclass
class Reasoning:
    """The uniform contract every capability must satisfy."""

    capability: str
    input: Any
    steps: List[str] = field(default_factory=list)
    output: Any = None
    confidence: float = 0.0
    evidence: List[str] = field(default_factory=list)
    at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "capability": self.capability,
            "input": self.input,
            "reasoning_process": list(self.steps),
            "output": self.output,
            "confidence": round(float(self.confidence), 4),
            "evidence": list(self.evidence),
            "at": self.at,
        }


class WorldModel:
    """Entity/relation/causal store backing the world-model capabilities."""

    def __init__(self, path: str = "data/world_model.json") -> None:
        self.path = path
        self.entities: Dict[str, Dict[str, Any]] = {}
        self.relations: List[Dict[str, Any]] = []
        self.causes: List[Dict[str, Any]] = []
        self.load()

    # ----------------------------------------------------------- persistence
    def load(self) -> None:
        if not os.path.exists(self.path):
            return
        try:
            with open(self.path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except (OSError, ValueError):
            return
        if isinstance(payload, dict):
            self.entities = dict(payload.get("entities") or {})
            self.relations = list(payload.get("relations") or [])
            self.causes = list(payload.get("causes") or [])

    def save(self) -> None:
        directory = os.path.dirname(self.path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        payload = {"entities": self.entities, "relations": self.relations, "causes": self.causes}
        temporary = self.path + ".tmp"
        with open(temporary, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, default=str)
        os.replace(temporary, self.path)

    # --------------------------------------------------------------- writing
    def observe(self, name: str, kind: str = "thing", **attributes: Any) -> Dict[str, Any]:
        key = str(name).strip().lower()
        if not key:
            raise ValueError("world-model entities need a name")
        entity = self.entities.setdefault(
            key,
            {"name": str(name), "kind": str(kind), "attributes": {}, "observations": 0, "first_seen": time.time()},
        )
        entity["kind"] = str(kind) or entity["kind"]
        entity["attributes"].update({str(k): v for k, v in attributes.items()})
        entity["observations"] += 1
        entity["last_seen"] = time.time()
        self.save()
        return entity

    def relate(self, source: str, relation: str, target: str, confidence: float = 0.6) -> Dict[str, Any]:
        for side in (source, target):
            if str(side).strip().lower() not in self.entities:
                self.observe(side)
        record = {
            "source": str(source).lower(),
            "relation": str(relation),
            "target": str(target).lower(),
            "confidence": float(confidence),
            "at": time.time(),
        }
        self.relations.append(record)
        self.save()
        return record

    def add_cause(self, cause: str, effect: str, observations: int = 1, confidence: float = 0.5) -> Dict[str, Any]:
        for existing in self.causes:
            if existing["cause"] == str(cause) and existing["effect"] == str(effect):
                existing["observations"] += int(observations)
                existing["confidence"] = min(
                    0.99, existing["confidence"] + 0.1 * int(observations)
                )
                existing["at"] = time.time()
                self.save()
                return existing
        record = {
            "cause": str(cause),
            "effect": str(effect),
            "observations": int(observations),
            "confidence": float(confidence),
            "at": time.time(),
        }
        self.causes.append(record)
        self.save()
        return record

    # --------------------------------------------------------------- reading
    def neighbours(self, name: str) -> List[Dict[str, Any]]:
        key = str(name).lower()
        return [
            item for item in self.relations if item["source"] == key or item["target"] == key
        ]

    def chain(self, cause: str, depth: int = 4) -> List[str]:
        """Forward causal chain, cycle-safe."""
        seen = {str(cause)}
        chain = [str(cause)]
        current = str(cause)
        for _ in range(int(depth)):
            following = [item for item in self.causes if item["cause"] == current]
            if not following:
                break
            best = max(following, key=lambda item: (item["confidence"], item["observations"]))
            if best["effect"] in seen:
                break
            current = best["effect"]
            seen.add(current)
            chain.append(current)
        return chain

    def snapshot(self) -> Dict[str, Any]:
        return {
            "entities": len(self.entities),
            "relations": len(self.relations),
            "causes": len(self.causes),
            "kinds": sorted({item["kind"] for item in self.entities.values()}),
        }

    def clear(self) -> None:
        self.entities = {}
        self.relations = []
        self.causes = []
        self.save()


class AGIEngine:
    """29 reasoning capabilities over the experience DB and world model."""

    def __init__(
        self,
        learner: Optional[LearningEngine] = None,
        world: Optional[WorldModel] = None,
    ) -> None:
        self.learning = learner or default_learning
        self.world = world or WorldModel()
        self.history: List[Reasoning] = []
        self.skills: Dict[str, Dict[str, Any]] = {}
        self.hypotheses: Dict[str, Dict[str, Any]] = {}

    # ----------------------------------------------------------- bookkeeping
    def _emit(self, reasoning: Reasoning) -> Dict[str, Any]:
        self.history.append(reasoning)
        if len(self.history) > 400:
            del self.history[:-400]
        return reasoning.to_dict()

    def traces(self, capability: str = "") -> List[Dict[str, Any]]:
        items = [item for item in self.history if not capability or item.capability == capability]
        return [item.to_dict() for item in items]

    @staticmethod
    def _overlap(left: str, right: str) -> float:
        first, second = set(tokenize(left)), set(tokenize(right))
        if not first or not second:
            return 0.0
        return len(first & second) / len(first | second)

    # ------------------------------------------------- transfer / analogies
    def transfer_learning(self, source_domain: str, target_domain: str, task: str) -> Dict[str, Any]:
        prior = self.learning.similar(source_domain + " " + task, limit=5)
        usable = [item for item in prior if item["success"]]
        steps = [
            "collected %d prior experiences from '%s'" % (len(prior), source_domain),
            "kept %d successful ones as transferable" % len(usable),
            "re-expressed each action for '%s'" % target_domain,
        ]
        transferred = [
            {
                "from": item["action"],
                "to": item["action"].replace(source_domain, target_domain)
                if source_domain in item["action"]
                else "%s (applied to %s)" % (item["action"], target_domain),
                "confidence": round(item["confidence"] * 0.8, 3),
            }
            for item in usable
        ]
        confidence = min(0.9, 0.2 + 0.15 * len(transferred))
        return self._emit(
            Reasoning(
                "transfer_learning",
                {"source": source_domain, "target": target_domain, "task": task},
                steps,
                transferred,
                confidence if transferred else 0.1,
                [item["id"] for item in usable],
            )
        )

    def cross_domain_reasoning(self, question: str, domains: Sequence[str]) -> Dict[str, Any]:
        contributions = []
        evidence: List[str] = []
        steps = []
        for domain in domains:
            matches = self.learning.similar(str(domain) + " " + question, limit=3)
            steps.append("queried domain '%s' -> %d experiences" % (domain, len(matches)))
            evidence.extend(item["id"] for item in matches)
            if matches:
                contributions.append(
                    {
                        "domain": str(domain),
                        "insight": matches[0]["action"],
                        "weight": round(matches[0]["rank_score"], 4),
                    }
                )
        contributions.sort(key=lambda item: item["weight"], reverse=True)
        synthesis = (
            "combined " + ", ".join(item["domain"] for item in contributions)
            if contributions
            else "no domain evidence available"
        )
        return self._emit(
            Reasoning(
                "cross_domain_reasoning",
                {"question": question, "domains": list(domains)},
                steps,
                {"synthesis": synthesis, "contributions": contributions},
                min(0.85, 0.15 * len(contributions) + 0.2) if contributions else 0.1,
                evidence,
            )
        )

    def abstract_reasoning(self, examples: Sequence[str]) -> Dict[str, Any]:
        token_sets = [set(tokenize(item)) for item in examples]
        shared = set.intersection(*token_sets) if token_sets else set()
        varying = sorted(set().union(*token_sets) - shared) if token_sets else []
        steps = [
            "tokenised %d examples" % len(examples),
            "invariant tokens: %s" % (sorted(shared) or "none"),
            "varying tokens treated as slots",
        ]
        pattern = " ".join(sorted(shared)) + " <slot>" if shared else "no shared structure"
        return self._emit(
            Reasoning(
                "abstract_reasoning",
                list(examples),
                steps,
                {"pattern": pattern, "invariants": sorted(shared), "slots": varying},
                min(0.9, len(shared) / max(1, len(set().union(*token_sets)) if token_sets else 1)),
                ["%d examples" % len(examples)],
            )
        )

    def analogical_reasoning(self, situation: str) -> Dict[str, Any]:
        matches = self.learning.similar(situation, limit=5)
        steps = ["searched experience database for structurally similar situations"]
        best = matches[0] if matches else None
        if best is not None:
            steps.append(
                "closest analogue '%s' (similarity %.2f)" % (best["action"], best.get("similarity", 0.0))
            )
        return self._emit(
            Reasoning(
                "analogical_reasoning",
                situation,
                steps,
                {
                    "analogue": best["action"] if best else None,
                    "mapping": "apply the analogue's action to the new situation" if best else "",
                    "alternatives": [item["action"] for item in matches[1:]],
                },
                best.get("similarity", 0.0) if best else 0.05,
                [item["id"] for item in matches],
            )
        )

    # --------------------------------------------------------------- causal
    def causal_reasoning(self, effect: str) -> Dict[str, Any]:
        candidates = [item for item in self.world.causes if item["effect"] == str(effect)]
        failures = self.learning.similar(effect, limit=5, kind="failure")
        steps = [
            "found %d recorded causes for '%s'" % (len(candidates), effect),
            "cross-checked %d recorded failures mentioning it" % len(failures),
        ]
        candidates.sort(key=lambda item: (item["confidence"], item["observations"]), reverse=True)
        return self._emit(
            Reasoning(
                "causal_reasoning",
                effect,
                steps,
                {
                    "likely_cause": candidates[0]["cause"] if candidates else None,
                    "all_causes": candidates,
                    "correlated_failures": [item["failure"] or item["error"] for item in failures],
                },
                candidates[0]["confidence"] if candidates else 0.1,
                ["world-model causal links"] + [item["id"] for item in failures],
            )
        )

    def causal_world_understanding(self, cause: str, depth: int = 4) -> Dict[str, Any]:
        chain = self.world.chain(cause, depth)
        steps = ["walked the causal graph forward from '%s'" % cause, "chain length %d" % len(chain)]
        return self._emit(
            Reasoning(
                "causal_world_understanding",
                {"cause": cause, "depth": depth},
                steps,
                {"chain": chain, "terminal_effect": chain[-1] if chain else None},
                min(0.9, 0.25 * len(chain)) if len(chain) > 1 else 0.1,
                ["%d causal edges known" % len(self.world.causes)],
            )
        )

    def counterfactual_reasoning(self, action: str, removed_condition: str) -> Dict[str, Any]:
        dependent = [
            item
            for item in self.world.causes
            if item["cause"] == str(removed_condition)
        ]
        history = self.learning.similar(action, limit=5)
        blocked = [item["effect"] for item in dependent]
        steps = [
            "removed condition '%s' from the world model" % removed_condition,
            "effects that lose their cause: %s" % (blocked or "none"),
            "checked %d historical attempts of the action" % len(history),
        ]
        would_succeed = not blocked and any(item["success"] for item in history)
        return self._emit(
            Reasoning(
                "counterfactual_reasoning",
                {"action": action, "without": removed_condition},
                steps,
                {
                    "would_succeed": would_succeed,
                    "blocked_effects": blocked,
                    "explanation": "'%s' is required for %s" % (removed_condition, blocked)
                    if blocked
                    else "no recorded dependency on that condition",
                },
                0.7 if blocked else (0.5 if history else 0.2),
                [item["id"] for item in history],
            )
        )

    def common_sense_reasoning(self, request: str) -> Dict[str, Any]:
        lowered = str(request).lower()
        hits = [
            {"trigger": trigger, "category": category, "note": note}
            for trigger, category, note in COMMON_SENSE_RULES
            if trigger in lowered
        ]
        steps = ["matched request against %d common-sense rules" % len(COMMON_SENSE_RULES)]
        if hits:
            steps.append("flagged: " + ", ".join(item["category"] for item in hits))
        return self._emit(
            Reasoning(
                "common_sense_reasoning",
                request,
                steps,
                {
                    "concerns": hits,
                    "needs_confirmation": any(
                        item["category"] in ("irreversible", "disruptive") for item in hits
                    ),
                },
                0.8 if hits else 0.4,
                [item["note"] for item in hits] or ["no rule matched"],
            )
        )

    # ------------------------------------------------ strategy and planning
    def strategic_reasoning(self, goal: str, options: Sequence[str]) -> Dict[str, Any]:
        scored = []
        evidence: List[str] = []
        for option in options:
            history = self.learning.similar(goal + " " + str(option), limit=4)
            wins = sum(1 for item in history if item["success"])
            losses = len(history) - wins
            warning = self.learning.avoid(goal, str(option))
            score = 0.5 + 0.12 * wins - 0.18 * losses - (0.5 if warning else 0.0)
            evidence.extend(item["id"] for item in history)
            scored.append(
                {
                    "option": str(option),
                    "score": round(score, 3),
                    "wins": wins,
                    "losses": losses,
                    "blocked": bool(warning),
                }
            )
        scored.sort(key=lambda item: item["score"], reverse=True)
        viable = [item for item in scored if not item["blocked"]]
        steps = [
            "scored %d options against recorded outcomes" % len(scored),
            "discarded %d options blocked by negative learning" % (len(scored) - len(viable)),
        ]
        return self._emit(
            Reasoning(
                "strategic_reasoning",
                {"goal": goal, "options": list(options)},
                steps,
                {"chosen": viable[0]["option"] if viable else None, "ranking": scored},
                viable[0]["score"] if viable else 0.1,
                evidence,
            )
        )

    def long_horizon_reasoning(self, goal: str, steps: Sequence[str], horizon_days: int = 30) -> Dict[str, Any]:
        plan = self.learning.adapt_plan(goal, steps)
        milestones = []
        per_step = max(1, int(horizon_days) // max(1, len(plan["ordered"]) or 1))
        for index, step in enumerate(plan["ordered"], start=1):
            milestones.append(
                {"order": index, "step": step, "target_day": index * per_step, "depends_on": plan["ordered"][: index - 1]}
            )
        process = [
            "used adaptive planning to order %d steps" % len(plan["steps"]),
            "assigned milestones across a %d day horizon" % horizon_days,
        ]
        return self._emit(
            Reasoning(
                "long_horizon_reasoning",
                {"goal": goal, "steps": list(steps), "horizon_days": horizon_days},
                process,
                {"milestones": milestones, "skipped": plan["skipped"]},
                0.6 if milestones else 0.1,
                [plan["evidence"]],
            )
        )

    def open_ended_problem_solving(self, problem: str, max_branches: int = 3) -> Dict[str, Any]:
        analogue = self.analogical_reasoning(problem)
        decomposition = [
            chunk.strip()
            for chunk in re.split(r"\band\b|,|;|\bthen\b", str(problem))
            if chunk.strip()
        ]
        branches = []
        for chunk in decomposition[: int(max_branches)]:
            matches = self.learning.similar(chunk, limit=2)
            branches.append(
                {
                    "subproblem": chunk,
                    "approach": matches[0]["action"] if matches else "explore: no prior experience",
                    "known": bool(matches),
                }
            )
        steps = [
            "decomposed the problem into %d subproblems" % len(decomposition),
            "attached a known approach to each subproblem where possible",
            "used the closest analogue as a global fallback",
        ]
        known = sum(1 for item in branches if item["known"])
        return self._emit(
            Reasoning(
                "open_ended_problem_solving",
                problem,
                steps,
                {
                    "branches": branches,
                    "fallback": analogue["output"]["analogue"],
                    "unknowns": [item["subproblem"] for item in branches if not item["known"]],
                },
                round(known / max(1, len(branches)), 3),
                ["analogical_reasoning"] + analogue["evidence"],
            )
        )

    def novel_problem_handling(self, problem: str) -> Dict[str, Any]:
        matches = self.learning.similar(problem, limit=3)
        novelty = 1.0 - (matches[0].get("similarity", 0.0) if matches else 0.0)
        steps = [
            "measured novelty against the experience database",
            "novelty score %.2f" % novelty,
        ]
        if novelty > 0.7:
            strategy = "decompose, run a small reversible probe, then verify before scaling"
            steps.append("treated as novel: chose cautious probe-first strategy")
        else:
            strategy = "reuse the closest known approach: %s" % matches[0]["action"]
            steps.append("treated as familiar: reused known approach")
        return self._emit(
            Reasoning(
                "novel_problem_handling",
                problem,
                steps,
                {"novelty": round(novelty, 3), "strategy": strategy, "probe_first": novelty > 0.7},
                round(1.0 - novelty / 2, 3),
                [item["id"] for item in matches] or ["no comparable experience"],
            )
        )

    def unknown_task_understanding(self, request: str) -> Dict[str, Any]:
        words = tokenize(request)
        verbs = [word for word in words if word.endswith("ise") or word.endswith("ize") or word in {
            "open", "close", "send", "find", "build", "make", "delete", "search", "run", "install", "write", "read"
        }]
        nouns = [word for word in words if word not in verbs]
        missing = []
        if not verbs:
            missing.append("no recognisable action verb")
        if not nouns:
            missing.append("no recognisable target")
        steps = [
            "extracted candidate actions %s" % (verbs or "[]"),
            "extracted candidate targets %s" % (nouns or "[]"),
            "listed missing information",
        ]
        question = (
            "What exactly should I do with '%s'?" % (" ".join(nouns[:3]) or request)
            if missing
            else ""
        )
        return self._emit(
            Reasoning(
                "unknown_task_understanding",
                request,
                steps,
                {
                    "action_candidates": verbs,
                    "target_candidates": nouns,
                    "missing": missing,
                    "clarifying_question": question,
                    "understood": not missing,
                },
                0.3 if missing else 0.7,
                ["lexical decomposition of the request"],
            )
        )

    # ------------------------------------------------- learning / adaptation
    def learn_new_task(self, name: str, steps: Sequence[str], domain: str = "general") -> Dict[str, Any]:
        skill = {
            "name": str(name),
            "domain": str(domain),
            "steps": [str(step) for step in steps],
            "runs": 0,
            "successes": 0,
            "learned_at": time.time(),
        }
        self.skills[str(name)] = skill
        self.learning.learn_workflow(name, steps, True)
        process = [
            "stored %d ordered steps as a reusable skill" % len(skill["steps"]),
            "registered the workflow in the experience database",
        ]
        return self._emit(
            Reasoning(
                "learn_new_task", {"name": name, "steps": list(steps)}, process, skill, 0.6,
                ["workflow experience recorded"],
            )
        )

    def practice_skill(self, name: str, success: bool) -> Dict[str, Any]:
        skill = self.skills.get(str(name))
        if skill is None:
            raise KeyError("unknown skill %s" % name)
        skill["runs"] += 1
        skill["successes"] += 1 if success else 0
        self.learning.learn_strategy(str(name), skill["domain"], success)
        return skill

    def cross_task_transfer(self, from_task: str, to_task: str) -> Dict[str, Any]:
        source = self.skills.get(str(from_task))
        steps = ["looked up the learned skill '%s'" % from_task]
        if source is None:
            return self._emit(
                Reasoning(
                    "cross_task_transfer", {"from": from_task, "to": to_task},
                    steps + ["skill not known; nothing to transfer"], None, 0.05,
                    ["skill registry"],
                )
            )
        reusable = [step for step in source["steps"] if self._overlap(step, to_task) > 0.0 or "verify" in step.lower()]
        transferred = {
            "name": str(to_task),
            "domain": source["domain"],
            "steps": reusable or list(source["steps"]),
            "runs": 0,
            "successes": 0,
            "derived_from": str(from_task),
            "learned_at": time.time(),
        }
        self.skills[str(to_task)] = transferred
        steps.append("carried over %d steps" % len(transferred["steps"]))
        rate = source["successes"] / source["runs"] if source["runs"] else 0.4
        return self._emit(
            Reasoning(
                "cross_task_transfer", {"from": from_task, "to": to_task}, steps, transferred,
                round(min(0.85, 0.3 + rate * 0.5), 3), ["source skill success rate %.2f" % rate],
            )
        )

    def knowledge_generalization(self, facts: Sequence[str]) -> Dict[str, Any]:
        abstraction = self.abstract_reasoning(facts)
        invariants = abstraction["output"]["invariants"]
        rule = (
            "whenever %s holds, the same conclusion applied in %d observed cases"
            % (" + ".join(invariants), len(facts))
            if invariants
            else "no generalisable rule found"
        )
        steps = ["abstracted the facts", "required at least 2 supporting facts before generalising"]
        confident = bool(invariants) and len(facts) >= 2
        return self._emit(
            Reasoning(
                "knowledge_generalization", list(facts), steps,
                {"rule": rule, "invariants": invariants, "generalised": confident},
                0.65 if confident else 0.15, ["%d source facts" % len(facts)],
            )
        )

    def skill_generalization(self, min_runs: int = 2) -> Dict[str, Any]:
        proven = [
            skill for skill in self.skills.values()
            if skill["runs"] >= int(min_runs) and skill["successes"] >= 1
        ]
        shared_steps: Dict[str, int] = {}
        for skill in proven:
            for step in skill["steps"]:
                shared_steps[step] = shared_steps.get(step, 0) + 1
        generic = sorted([step for step, count in shared_steps.items() if count > 1])
        steps = [
            "considered %d skills with at least %d runs" % (len(proven), min_runs),
            "extracted steps reused by more than one skill",
        ]
        return self._emit(
            Reasoning(
                "skill_generalization", {"min_runs": min_runs}, steps,
                {"generic_procedure": generic, "from_skills": [skill["name"] for skill in proven]},
                0.6 if generic else 0.1, ["skill registry statistics"],
            )
        )

    def strategy_generalization(self) -> Dict[str, Any]:
        stats = [item for item in self.learning.strategy_stats() if item["samples"] >= 2]
        by_domain: Dict[str, List[Dict[str, Any]]] = {}
        for item in stats:
            by_domain.setdefault(item["domain"], []).append(item)
        rules = []
        for domain, items in by_domain.items():
            best = max(items, key=lambda entry: (entry["success_rate"], entry["samples"]))
            if best["success_rate"] >= 0.6:
                rules.append(
                    {
                        "domain": domain,
                        "default_strategy": best["name"],
                        "success_rate": best["success_rate"],
                        "samples": best["samples"],
                    }
                )
        steps = [
            "grouped %d strategies with >=2 samples by domain" % len(stats),
            "promoted only strategies above a 60%% success rate",
        ]
        return self._emit(
            Reasoning(
                "strategy_generalization", {}, steps, {"default_strategies": rules},
                0.6 if rules else 0.1, ["strategy statistics table"],
            )
        )

    def continual_adaptation(self, window: int = 10) -> Dict[str, Any]:
        stats = self.learning.stats()
        recent_failures = stats["by_type"].get("failure", {}).get("count", 0)
        recent_successes = stats["by_type"].get("success", {}).get("count", 0)
        total = recent_failures + recent_successes
        rate = recent_successes / total if total else 0.0
        if total < 3:
            adjustment = "hold: not enough evidence to change behaviour"
        elif rate < 0.5:
            adjustment = "increase verification and ask for confirmation more often"
        elif rate > 0.85:
            adjustment = "reduce redundant confirmations for proven actions"
        else:
            adjustment = "keep the current balance of autonomy and verification"
        steps = [
            "measured the recent success rate (%.2f over %d samples)" % (rate, total),
            "required at least 3 samples before adapting",
        ]
        return self._emit(
            Reasoning(
                "continual_adaptation", {"window": window}, steps,
                {"success_rate": round(rate, 3), "adjustment": adjustment, "samples": total},
                0.7 if total >= 3 else 0.2, ["experience database statistics"],
            )
        )

    def self_directed_learning(self, limit: int = 3) -> Dict[str, Any]:
        stats = self.learning.stats()
        gaps: List[Dict[str, Any]] = []
        failures = self.learning.similar("failure error problem", limit=10, kind="failure")
        for item in failures:
            gaps.append({"topic": item["action"], "reason": item["failure"] or "repeated failure"})
        for skill in self.skills.values():
            if skill["runs"] and skill["successes"] / skill["runs"] < 0.5:
                gaps.append({"topic": skill["name"], "reason": "skill success rate below 50%"})
        agenda = gaps[: int(limit)]
        steps = [
            "scanned failures and weak skills for knowledge gaps",
            "built a bounded study agenda (limit %d)" % limit,
        ]
        return self._emit(
            Reasoning(
                "self_directed_learning", {"limit": limit}, steps,
                {"agenda": agenda, "total_gaps": len(gaps), "experiences": stats["total"]},
                0.6 if agenda else 0.2, ["failure experiences", "skill registry"],
            )
        )

    def curiosity_exploration(self, limit: int = 3) -> Dict[str, Any]:
        unexplored = [
            entity for entity in self.world.entities.values()
            if entity["observations"] <= 1 and not self.world.neighbours(entity["name"])
        ]
        questions = [
            "What is '%s' related to?" % entity["name"] for entity in unexplored[: int(limit)]
        ]
        steps = [
            "looked for entities with a single observation and no relations",
            "generated bounded exploration questions (never an open loop)",
        ]
        return self._emit(
            Reasoning(
                "curiosity_exploration", {"limit": limit}, steps,
                {"questions": questions, "candidates": len(unexplored), "bounded": True},
                0.5 if questions else 0.15, ["world model sparsity"],
            )
        )

    # ------------------------------------------- hypotheses and experiments
    def hypothesis_generation(self, observation: str) -> Dict[str, Any]:
        related = self.learning.similar(observation, limit=5)
        causes = [item for item in self.world.causes if item["effect"] in observation]
        proposals = []
        for item in causes:
            proposals.append({"statement": "%s causes %s" % (item["cause"], item["effect"]), "prior": item["confidence"]})
        for item in related:
            if not item["success"] and (item["error"] or item["failure"]):
                proposals.append(
                    {
                        "statement": "%s is caused by %s" % (observation, item["error"] or item["failure"]),
                        "prior": round(item["confidence"] * 0.7, 3),
                    }
                )
        if not proposals:
            proposals.append({"statement": "%s is caused by an unmodelled factor" % observation, "prior": 0.2})
        recorded = []
        for proposal in proposals[:5]:
            hypothesis_id = "HYP-" + uuid.uuid4().hex[:6]
            self.hypotheses[hypothesis_id] = {
                "id": hypothesis_id,
                "statement": proposal["statement"],
                "prior": proposal["prior"],
                "status": "open",
                "trials": [],
                "created_at": time.time(),
            }
            recorded.append(self.hypotheses[hypothesis_id])
        steps = [
            "gathered %d causal links and %d related experiences" % (len(causes), len(related)),
            "formed %d falsifiable hypotheses" % len(recorded),
        ]
        return self._emit(
            Reasoning(
                "hypothesis_generation", observation, steps, recorded,
                max(item["prior"] for item in recorded), [item["id"] for item in related],
            )
        )

    def hypothesis_testing(self, hypothesis_id: str, test: Callable[[], bool], trials: int = 3) -> Dict[str, Any]:
        hypothesis = self.hypotheses.get(str(hypothesis_id))
        if hypothesis is None:
            raise KeyError("unknown hypothesis %s" % hypothesis_id)
        outcomes: List[bool] = []
        errors: List[str] = []
        for _ in range(max(1, int(trials))):
            try:
                outcomes.append(bool(test()))
            except Exception as error:  # a failed experiment is data, not a crash
                outcomes.append(False)
                errors.append("%s: %s" % (type(error).__name__, error))
        supported = sum(1 for item in outcomes if item)
        ratio = supported / len(outcomes)
        hypothesis["trials"].extend(outcomes)
        hypothesis["status"] = "supported" if ratio >= 0.67 else ("rejected" if ratio <= 0.33 else "inconclusive")
        hypothesis["posterior"] = round((hypothesis["prior"] + ratio) / 2, 3)
        self.learning.record(
            "hypothesis:" + hypothesis["statement"], "tested %d trials" % len(outcomes),
            hypothesis["status"], ratio >= 0.67, "experience", error="; ".join(errors),
            confidence=hypothesis["posterior"],
        )
        steps = [
            "ran %d independent trials" % len(outcomes),
            "%d supported the hypothesis" % supported,
            "updated the posterior from the prior and the observed ratio",
        ]
        return self._emit(
            Reasoning(
                "hypothesis_testing", {"id": hypothesis_id, "trials": trials}, steps, hypothesis,
                hypothesis["posterior"], errors or ["%d/%d trials supported" % (supported, len(outcomes))],
            )
        )

    def experiment_planning(self, hypothesis_id: str) -> Dict[str, Any]:
        hypothesis = self.hypotheses.get(str(hypothesis_id))
        if hypothesis is None:
            raise KeyError("unknown hypothesis %s" % hypothesis_id)
        plan = [
            {"step": "define the measurable signal that would falsify the hypothesis", "reversible": True},
            {"step": "prepare an isolated environment (no destructive actions)", "reversible": True},
            {"step": "run 3 trials and record every outcome", "reversible": True},
            {"step": "compare against the control condition", "reversible": True},
            {"step": "record the result as an experience and update the world model", "reversible": True},
        ]
        steps = ["derived a reversible, falsifiable experiment for the hypothesis"]
        return self._emit(
            Reasoning(
                "experiment_planning", hypothesis["statement"], steps,
                {"plan": plan, "destructive": False, "trials": 3}, 0.7,
                ["hypothesis prior %.2f" % hypothesis["prior"]],
            )
        )

    # ---------------------------------------------------------- world model
    def world_model_construction(self, observations: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
        added = 0
        for observation in observations:
            if "relation" in observation:
                self.world.relate(
                    observation["source"], observation["relation"], observation["target"],
                    float(observation.get("confidence", 0.6)),
                )
            elif "cause" in observation:
                self.world.add_cause(
                    observation["cause"], observation["effect"],
                    int(observation.get("observations", 1)),
                    float(observation.get("confidence", 0.5)),
                )
            else:
                self.world.observe(
                    observation.get("name", ""), observation.get("kind", "thing"),
                    **{k: v for k, v in observation.items() if k not in ("name", "kind")},
                )
            added += 1
        snapshot = self.world.snapshot()
        steps = ["ingested %d observations" % added, "world model now %s" % snapshot]
        return self._emit(
            Reasoning(
                "world_model_construction", {"observations": added}, steps, snapshot,
                min(0.9, 0.2 + 0.05 * snapshot["entities"]), ["persisted to %s" % self.world.path],
            )
        )

    def environment_modeling(self, probe: Optional[Callable[[], Dict[str, Any]]] = None) -> Dict[str, Any]:
        environment: Dict[str, Any] = {}
        steps = []
        if probe is not None:
            try:
                environment.update(probe() or {})
                steps.append("probed the live environment")
            except Exception as error:
                steps.append("probe failed: %s" % error)
        try:
            import platform

            environment.setdefault("os", platform.system())
            environment.setdefault("python", platform.python_version())
            steps.append("read platform information")
        except Exception as error:  # pragma: no cover - platform is stdlib
            steps.append("platform unavailable: %s" % error)
        for key, value in environment.items():
            self.world.observe(str(key), "environment", value=value)
        constraints = []
        if str(environment.get("network", "")).lower() in ("offline", "false", "none"):
            constraints.append("no network: cloud and integration actions will fail")
        if environment.get("gpu") in (None, False, "none"):
            constraints.append("no GPU: prefer small local models")
        return self._emit(
            Reasoning(
                "environment_modeling", {"probe": probe is not None}, steps,
                {"environment": environment, "constraints": constraints}, 0.75,
                ["%d environment entities stored" % len(environment)],
            )
        )

    # ------------------------------------------------------------ expansion
    def capability_expansion(self) -> Dict[str, Any]:
        agenda = self.self_directed_learning(limit=5)["output"]["agenda"]
        generic = self.skill_generalization()["output"]["generic_procedure"]
        new_capabilities = []
        for gap in agenda:
            name = "handle_" + re.sub(r"[^a-z0-9]+", "_", str(gap["topic"]).lower())[:32].strip("_")
            if name in self.skills or not name.strip("_"):
                continue
            proposed_steps = generic or [
                "inspect the target", "attempt a reversible action", "verify the outcome",
            ]
            self.skills[name] = {
                "name": name,
                "domain": "expansion",
                "steps": list(proposed_steps),
                "runs": 0,
                "successes": 0,
                "learned_at": time.time(),
                "source_gap": gap["topic"],
            }
            new_capabilities.append(name)
        steps = [
            "used the study agenda to identify missing capabilities",
            "seeded each with the generalised procedure",
            "new capabilities start unproven (runs=0)",
        ]
        return self._emit(
            Reasoning(
                "capability_expansion", {}, steps,
                {"new_capabilities": new_capabilities, "unproven": True},
                0.5 if new_capabilities else 0.15, ["self-directed learning agenda"],
            )
        )

    def novel_strategy_discovery(self, domain: str = "general") -> Dict[str, Any]:
        stats = [item for item in self.learning.strategy_stats() if item["domain"] == domain or not domain]
        weak = [item for item in stats if item["samples"] >= 2 and item["success_rate"] < 0.5]
        strong = [item for item in stats if item["success_rate"] >= 0.6]
        proposals = []
        for item in weak:
            donor = strong[0]["name"] if strong else "verify-before-act"
            proposals.append(
                {
                    "name": "%s+%s" % (item["name"], donor),
                    "replaces": item["name"],
                    "rationale": "%s fails %.0f%% of the time; graft the proven '%s' approach"
                    % (item["name"], (1 - item["success_rate"]) * 100, donor),
                    "validated": False,
                }
            )
        steps = [
            "found %d weak and %d strong strategies" % (len(weak), len(strong)),
            "proposed recombinations; none adopted until tested",
        ]
        return self._emit(
            Reasoning(
                "novel_strategy_discovery", {"domain": domain}, steps,
                {"proposals": proposals}, 0.45 if proposals else 0.1,
                ["strategy success statistics"],
            )
        )

    def autonomous_knowledge_acquisition(
        self, fetcher: Optional[Callable[[str], str]] = None, limit: int = 2
    ) -> Dict[str, Any]:
        questions = self.curiosity_exploration(limit=limit)["output"]["questions"]
        acquired: List[Dict[str, Any]] = []
        steps = ["took %d bounded questions from curiosity" % len(questions)]
        if fetcher is None:
            steps.append("no knowledge source supplied; nothing fetched")
            return self._emit(
                Reasoning(
                    "autonomous_knowledge_acquisition", {"limit": limit}, steps,
                    {"questions": questions, "acquired": [], "source_required": True}, 0.2,
                    ["IMPLEMENTATION VERIFIED - requires a knowledge source"],
                )
            )
        for question in questions:
            try:
                answer = str(fetcher(question))
            except Exception as error:
                steps.append("fetch failed for '%s': %s" % (question, error))
                continue
            if not answer.strip():
                continue
            record = self.learning.record(
                "acquired:" + question, "stored answer", answer, True, "experience",
                confidence=0.5, importance=0.5, source="autonomous",
            )
            acquired.append({"question": question, "answer": answer, "experience_id": record["id"]})
        steps.append("stored %d answers with their source" % len(acquired))
        return self._emit(
            Reasoning(
                "autonomous_knowledge_acquisition", {"limit": limit}, steps,
                {"acquired": acquired}, 0.6 if acquired else 0.2,
                [item["experience_id"] for item in acquired] or ["no answers returned"],
            )
        )

    # ----------------------------------------------------------- reflection
    def capability_report(self) -> Dict[str, Any]:
        exercised = {item.capability for item in self.history}
        return {
            "capabilities": list(CAPABILITIES),
            "count": len(CAPABILITIES),
            "exercised": sorted(exercised),
            "implemented": sorted(
                name for name in CAPABILITIES if callable(getattr(self, name, None))
            ),
            "skills": len(self.skills),
            "hypotheses": len(self.hypotheses),
            "world": self.world.snapshot(),
            "disclaimer": "engineering equivalents with measurable behaviour; not true AGI",
        }


agi = AGIEngine()
