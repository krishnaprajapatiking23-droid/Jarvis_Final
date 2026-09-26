"""AGI foundation tests: uncertainty, trace, world model, goals.

These are written to *break* the implementation rather than confirm it. Each
test isolates its store in a temporary directory so a test run never reads or
writes the live ``data/`` files.
"""

from __future__ import annotations

import os
import tempfile
import time
import unittest

from agi.goals import (
    ABANDONED,
    ACTIVE,
    COMPLETED,
    Constraint,
    GoalHierarchy,
    Objective,
)
from agi.trace import Trace
from agi.uncertainty import Belief, Evidence, ambiguous, combine
from agi.world_model import WorldModel


def temp_path(name: str) -> str:
    return os.path.join(tempfile.mkdtemp(prefix="agi_test_"), name)


class UncertaintyTests(unittest.TestCase):

    def test_no_evidence_is_unknown_not_neutral_truth(self):
        belief = Belief("chrome is running")

        self.assertEqual(belief.level(), "unknown")
        self.assertTrue(belief.needs_human())

    def test_supporting_evidence_raises_confidence(self):
        belief = Belief(True)
        before = belief.confidence
        belief.support(Evidence("process list", True, 0.9, verified=True))

        self.assertGreater(belief.confidence, before)
        self.assertEqual(belief.level(), "known")

    def test_one_strong_refutation_outweighs_several_weak_confirmations(self):
        """Log-odds must not let weak agreement drown a strong contradiction."""

        belief = Belief(True)

        for _ in range(3):
            belief.support(Evidence("weak hint", True, 0.2))

        with_weak = belief.confidence
        belief.refute(Evidence("direct observation", False, 0.95, verified=True))

        self.assertLess(belief.confidence, with_weak)
        self.assertLess(belief.confidence, 0.5)

    def test_confidence_never_reaches_certainty_from_one_source(self):
        belief = Belief(True)
        belief.support(Evidence("single source", True, 1.0, verified=True))

        self.assertLess(belief.confidence, 1.0)

    def test_assumptions_cap_confidence(self):
        belief = Belief(True)

        for _ in range(5):
            belief.support(Evidence("strong", True, 0.95, verified=True))

        without = belief.confidence
        belief.assume("the file has not been moved since")

        self.assertLess(belief.confidence, without)

    def test_evidence_decays_with_age(self):
        old = Evidence("stale source", True, 0.9, at=time.time() - 60 * 24 * 3600)
        fresh = Evidence("fresh source", True, 0.9)

        self.assertLess(old.weight(), fresh.weight())

    def test_verified_evidence_decays_more_slowly(self):
        age = time.time() - 14 * 24 * 3600
        plain = Evidence("s", True, 0.9, at=age)
        verified = Evidence("s", True, 0.9, verified=True, at=age)

        self.assertGreater(verified.weight(), plain.weight())

    def test_combine_all_is_stricter_than_any(self):
        beliefs = [Belief(True, 0.6), Belief(True, 0.6)]

        self.assertLess(combine(beliefs, "all"), combine(beliefs, "any"))

    def test_combine_empty_is_zero_not_one(self):
        self.assertEqual(combine([]), 0.0)

    def test_ambiguous_detects_a_close_call(self):
        self.assertTrue(ambiguous({"a": 0.51, "b": 0.49}))
        self.assertFalse(ambiguous({"a": 0.9, "b": 0.1}))
        self.assertFalse(ambiguous({"a": 1.0}))

    def test_round_trip_through_storage_preserves_confidence(self):
        belief = Belief("x", 0.5)
        belief.support(Evidence("a", True, 0.8, verified=True))
        belief.assume("unchecked premise")

        restored = Belief.from_dict(belief.to_dict())

        self.assertAlmostEqual(restored.confidence, belief.confidence, places=3)
        self.assertEqual(restored.assumptions, belief.assumptions)

    def test_explain_reports_real_counts(self):
        belief = Belief(True)
        belief.support(Evidence("a", True, 0.7))
        belief.refute(Evidence("b", False, 0.5))
        text = belief.explain()

        self.assertIn("1 supporting", text)
        self.assertIn("1 opposing", text)


class WorldModelTests(unittest.TestCase):

    def setUp(self):
        self.world = WorldModel(temp_path("world.json"))

    def test_observation_beats_assumption(self):
        self.world.observe("chrome", "running", True, source="process list")
        self.world.assume("chrome", "running", False, "guessed")

        self.assertIs(self.world.value("chrome", "running"), True)

    def test_assumption_stays_low_confidence(self):
        belief = self.world.assume("vscode", "running", True, "not checked")

        self.assertLess(belief.confidence, 0.6)
        self.assertNotEqual(belief.level(), "known")

    def test_changed_value_replaces_rather_than_averages(self):
        self.world.observe("chrome", "running", True, source="a")
        self.world.observe("chrome", "running", True, source="b")
        self.world.observe("chrome", "running", False, source="c")

        belief = self.world.get("chrome", "running")

        self.assertIs(belief.value, False)
        self.assertGreater(belief.confidence, 0.6)

    def test_state_change_records_an_event(self):
        self.world.observe("chrome", "running", True, source="a")
        self.world.observe("chrome", "running", False, source="b")
        events = self.world.events("state_change")

        self.assertEqual(len(events), 1)
        self.assertIs(events[0]["was"], True)
        self.assertIs(events[0]["now"], False)

    def test_stale_fact_is_downgraded_not_reported_as_current(self):
        belief = self.world.observe("chrome", "running", True, source="a")
        self.assertEqual(belief.level(), "known")

        # Age it past the freshness window for a process fact.
        belief.updated = time.time() - 3600
        refreshed = self.world.get("chrome", "running")

        self.assertTrue(any("not re-observed" in a for a in refreshed.assumptions))
        self.assertNotEqual(refreshed.level(), "known")

    def test_staleness_note_does_not_stack(self):
        belief = self.world.observe("chrome", "running", True, source="a")
        belief.updated = time.time() - 3600

        for _ in range(4):
            self.world.get("chrome", "running")

        notes = [
            a for a in self.world.get("chrome", "running").assumptions
            if a.startswith("not re-observed")
        ]

        self.assertEqual(len(notes), 1)

    def test_unknown_entity_returns_none_not_a_default(self):
        self.assertIsNone(self.world.get("nothing", "at all"))
        self.assertIsNone(self.world.value("nothing", "at all"))
        self.assertFalse(self.world.known("nothing", "at all"))

    def test_contradiction_is_detected(self):
        self.world.observe("db", "reachable", True, source="ping", strength=0.6)
        self.world.contradict("db", "reachable", source="query timeout", strength=0.6)

        self.assertTrue(self.world.contradictions())

    def test_dependency_closure_is_transitive(self):
        self.world.relate("app", "depends_on", "library")
        self.world.relate("library", "depends_on", "runtime")

        self.assertIn("app", self.world.depends_on("runtime"))

    def test_relations_do_not_duplicate(self):
        self.world.relate("a", "depends_on", "b")
        self.world.relate("a", "depends_on", "b")

        self.assertEqual(len(self.world.relations(subject="a")), 1)

    def test_survives_restart(self):
        path = temp_path("persist.json")
        first = WorldModel(path)
        first.observe("project", "state", "modified", source="editor", kind="project")
        first.relate("project", "depends_on", "python")

        second = WorldModel(path)

        self.assertEqual(second.value("project", "state"), "modified")
        self.assertEqual(len(second.relations(subject="project")), 1)

    def test_forget_removes_entity_and_its_relations(self):
        self.world.observe("temp", "exists", True, source="fs")
        self.world.relate("temp", "depends_on", "disk")
        self.world.forget("temp")

        self.assertIsNone(self.world.get("temp", "exists"))
        self.assertEqual(self.world.relations(subject="temp"), [])


class GoalTests(unittest.TestCase):

    def setUp(self):
        self.goals = GoalHierarchy(temp_path("goals.json"))

    def test_progress_rolls_up_from_leaves(self):
        project = self.goals.create("release", level="PROJECT")
        a = self.goals.create("task a", level="TASK", parent=project.id)
        self.goals.create("task b", level="TASK", parent=project.id)

        self.goals.set_progress(a.id, 1.0)

        self.assertAlmostEqual(self.goals.get(project.id).progress, 0.5, places=2)

    def test_parent_cannot_complete_while_a_child_is_open(self):
        project = self.goals.create("release", level="PROJECT")
        a = self.goals.create("task a", level="TASK", parent=project.id)
        b = self.goals.create("task b", level="TASK", parent=project.id)

        self.goals.set_progress(a.id, 1.0)
        self.goals.set_progress(b.id, 0.99)

        parent = self.goals.get(project.id)

        self.assertNotEqual(parent.status, COMPLETED)
        self.assertLess(parent.progress, 1.0)

    def test_completing_every_child_completes_the_parent(self):
        project = self.goals.create("release", level="PROJECT")
        a = self.goals.create("task a", level="TASK", parent=project.id)
        b = self.goals.create("task b", level="TASK", parent=project.id)

        self.goals.set_progress(a.id, 1.0)
        self.goals.set_progress(b.id, 1.0)

        self.assertEqual(self.goals.get(project.id).status, COMPLETED)

    def test_dependencies_block_readiness(self):
        first = self.goals.create("build", level="TASK")
        second = self.goals.create("deploy", level="TASK", depends_on=[first.id])

        ready = {g.id for g in self.goals.ready()}

        self.assertIn(first.id, ready)
        self.assertNotIn(second.id, ready)

    def test_next_action_is_a_leaf_not_a_parent(self):
        project = self.goals.create("release", level="PROJECT")
        leaf = self.goals.create("run tests", level="TASK", parent=project.id)

        self.assertEqual(self.goals.next_action().id, leaf.id)

    def test_competing_objectives_are_surfaced(self):
        goal = self.goals.create(
            "finish quickly but do not break anything",
            objectives=[Objective("speed", 0.8), Objective("correctness", 0.9)],
        )

        self.assertTrue(goal.tradeoff()["competing"])

    def test_single_objective_is_not_reported_as_competing(self):
        goal = self.goals.create("x", objectives=[Objective("speed", 0.8)])

        self.assertFalse(goal.tradeoff()["competing"])

    def test_constraint_violation_is_detected(self):
        goal = self.goals.create(
            "x", constraints=[Constraint("time", "under 60s", limit=60)]
        )

        self.assertTrue(goal.violations({"time": 90}))
        self.assertFalse(goal.violations({"time": 30}))

    def test_deadline_raises_priority_score(self):
        relaxed = self.goals.create("later", priority=0.5, urgency=0.5)
        urgent = self.goals.create(
            "now", priority=0.5, urgency=0.5, deadline=time.time() + 60
        )

        self.assertGreater(urgent.score(), relaxed.score())

    def test_abandoning_a_parent_cascades(self):
        project = self.goals.create("release", level="PROJECT")
        child = self.goals.create("task", level="TASK", parent=project.id)

        self.goals.set_status(project.id, ABANDONED)

        self.assertEqual(self.goals.get(child.id).status, ABANDONED)

    def test_unknown_parent_is_rejected(self):
        with self.assertRaises(KeyError):
            self.goals.create("orphan", parent="does-not-exist")

    def test_invalid_level_is_rejected(self):
        with self.assertRaises(ValueError):
            self.goals.create("x", level="NOT_A_LEVEL")

    def test_empty_description_is_rejected(self):
        with self.assertRaises(ValueError):
            self.goals.create("   ")

    def test_survives_restart(self):
        path = temp_path("goals_persist.json")
        first = GoalHierarchy(path)
        goal = first.create("long running goal", level="LONG_TERM")

        second = GoalHierarchy(path)
        restored = second.get(goal.id)

        self.assertIsNotNone(restored)
        self.assertEqual(restored.description, "long running goal")
        self.assertTrue(second.resumable())


class TraceTests(unittest.TestCase):

    def test_stage_order_is_checked_not_just_membership(self):
        trace = Trace.start("x")
        trace.stage("execution")
        trace.stage("planning")

        self.assertFalse(trace.covered(("planning", "execution")))

    def test_covered_accepts_correct_order(self):
        trace = Trace.start("x")
        trace.stage("planning")
        trace.stage("execution")

        self.assertTrue(trace.covered(("planning", "execution")))

    def test_first_failure_is_recorded_as_the_failure_stage(self):
        trace = Trace.start("x")
        trace.stage("planning", ok=True)
        trace.stage("execution", ok=False, error="boom")
        trace.stage("verification", ok=False)

        self.assertEqual(trace.failure_stage, "execution")

    def test_open_stage_measures_duration(self):
        trace = Trace.start("x")
        trace.open("reasoning")
        time.sleep(0.01)
        trace.stage("reasoning")

        self.assertGreater(trace.steps[0].duration, 0)

    def test_lessons_do_not_duplicate(self):
        trace = Trace.start("x")
        trace.learn("same lesson")
        trace.learn("same lesson")

        self.assertEqual(len(trace.lessons), 1)

    def test_report_is_serialisable(self):
        import json

        trace = Trace.start("x")
        trace.stage("intent")
        trace.select("s", "because")
        trace.finish("completed", verified=True, persist=False)

        self.assertIsInstance(json.dumps(trace.report()), str)


if __name__ == "__main__":
    unittest.main(verbosity=2)
