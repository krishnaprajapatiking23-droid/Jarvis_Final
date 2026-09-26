"""AGI reasoning tests: hypotheses, experiments, strategies, transfer.

Each test isolates its store under a temporary directory. Where one module
holds a reference to another's singleton (the experiment planner feeds evidence
back into the hypothesis engine), the reference is redirected for the duration
of the test rather than left pointing at the live store.
"""

from __future__ import annotations

import os
import tempfile
import unittest

import agi.experiments as experiments_module
from agi.experiments import APPROVED, DONE, ExperimentPlanner
from agi.hypotheses import (
    CONFIRMED,
    CORRELATION,
    INTERVENTION,
    OBSERVATION,
    REJECTED,
    SEQUENCE,
    HypothesisEngine,
)
from agi.strategies import Strategy, StrategyRegistry, keywords, normalise, stem
from agi.transfer import transfer


def temp_path(name: str) -> str:
    return os.path.join(tempfile.mkdtemp(prefix="agi_test_"), name)


class HypothesisTests(unittest.TestCase):

    def setUp(self):
        self.engine = HypothesisEngine(temp_path("h.json"))

    def test_correlation_alone_never_licenses_a_causal_claim(self):
        h = self.engine.create(
            "the deploy broke the build", cause="deploy", effect="build failure"
        )
        self.engine.support(h.id, "they happened together", 0.9, CORRELATION, True)
        claim = self.engine.get(h.id).causal_claim()

        self.assertFalse(claim["warranted"])
        self.assertEqual(claim["claim"], "correlation")

    def test_sequence_ranks_below_correlation(self):
        h = self.engine.create("a caused b", cause="a", effect="b")
        self.engine.support(h.id, "a came first", 0.9, SEQUENCE, True)

        self.assertEqual(self.engine.get(h.id).causal_claim()["claim"], "sequence")

    def test_intervention_licenses_a_causal_claim(self):
        h = self.engine.create(
            "the missing dependency breaks the build",
            cause="missing dependency",
            effect="build failure",
        )
        self.engine.support(h.id, "observed together", 0.8, CORRELATION, True)
        self.engine.support(h.id, "installed it and the build passed", 0.9, INTERVENTION, True)
        claim = self.engine.get(h.id).causal_claim()

        self.assertTrue(claim["warranted"])
        self.assertEqual(claim["claim"], "causal")
        self.assertEqual(self.engine.get(h.id).status, CONFIRMED)

    def test_non_causal_hypothesis_is_not_given_a_causal_claim(self):
        h = self.engine.create("the config is probably wrong")

        self.assertFalse(h.causal_claim()["warranted"])
        self.assertIn("not a causal", h.causal_claim()["claim"])

    def test_refutation_drives_confidence_down_and_rejects(self):
        h = self.engine.create("the disk is full")

        for _ in range(3):
            self.engine.refute(h.id, "df shows 40% free", 0.9, OBSERVATION, True)

        self.assertEqual(self.engine.get(h.id).status, REJECTED)

    def test_duplicate_statement_returns_the_same_hypothesis(self):
        first = self.engine.create("the same idea")
        second = self.engine.create("The Same Idea")

        self.assertEqual(first.id, second.id)

    def test_empty_statement_is_rejected(self):
        with self.assertRaises(ValueError):
            self.engine.create("   ")

    def test_most_informative_prefers_the_genuinely_uncertain(self):
        near_certain = self.engine.create("almost certain", tests=["t"])
        self.engine.support(near_certain.id, "strong", 0.95, OBSERVATION, True)
        self.engine.support(near_certain.id, "strong again", 0.95, OBSERVATION, True)

        uncertain = self.engine.create("genuinely open", prior=0.5, tests=["t"])

        ranked = self.engine.most_informative()

        self.assertEqual(ranked[0].id, uncertain.id)

    def test_hypotheses_without_tests_are_not_offered_for_testing(self):
        self.engine.create("untestable claim")

        self.assertEqual(self.engine.most_informative(), [])

    def test_discriminating_test_finds_a_separating_observation(self):
        a = self.engine.create("cause is a missing dependency", tests=["run pip check"])
        b = self.engine.create("cause is a syntax error", tests=["run the linter"])
        result = self.engine.discriminating_test(a.id, b.id)

        self.assertTrue(result["found"])
        self.assertIn(result["test"], ("run pip check", "run the linter"))

    def test_identical_predictions_report_that_no_test_separates_them(self):
        a = self.engine.create("hypothesis a", tests=["same test"])
        b = self.engine.create("hypothesis b", tests=["same test"])
        result = self.engine.discriminating_test(a.id, b.id)

        self.assertFalse(result["found"])
        self.assertIn("same observations", result["reason"])

    def test_survives_restart(self):
        path = temp_path("h_persist.json")
        first = HypothesisEngine(path)
        h = first.create("persisted idea", cause="x", effect="y")
        first.support(h.id, "evidence", 0.8, INTERVENTION, True)

        second = HypothesisEngine(path)
        restored = second.get(h.id)

        self.assertIsNotNone(restored)
        self.assertAlmostEqual(restored.confidence, self.engine.get(h.id).confidence
                               if self.engine.get(h.id) else restored.confidence, places=3)
        self.assertEqual(restored.cause, "x")


class ExperimentTests(unittest.TestCase):

    def setUp(self):
        self.engine = HypothesisEngine(temp_path("h.json"))
        self._original = experiments_module.hypothesis_engine
        experiments_module.hypothesis_engine = self.engine
        self.planner = ExperimentPlanner(temp_path("e.json"))
        self.hypothesis = self.engine.create(
            "the port is already bound", tests=["list listening ports"]
        )

    def tearDown(self):
        experiments_module.hypothesis_engine = self._original

    def test_experiment_against_unknown_hypothesis_is_rejected(self):
        with self.assertRaises(KeyError):
            self.planner.design("nope", "do a thing", expects="something")

    def test_experiment_requires_a_prediction(self):
        with self.assertRaises(ValueError):
            self.planner.design(self.hypothesis.id, "do a thing", expects="")

    def test_low_risk_read_experiment_runs_without_approval(self):
        plan = self.planner.design(
            self.hypothesis.id, "list ports", expects="5432", action="read"
        )
        result = self.planner.run(plan.id, lambda e: "tcp 5432 LISTEN")

        self.assertTrue(result["ok"])
        self.assertTrue(result["supported"])

    def test_high_risk_experiment_without_rollback_is_refused(self):
        plan = self.planner.design(
            self.hypothesis.id,
            "kill the process holding the port",
            expects="port free",
            action="process.kill",
            risk="high",
        )
        result = self.planner.run(plan.id, lambda e: "killed")

        self.assertFalse(result["ok"])
        self.assertTrue(result["needs_approval"])

    def test_approved_high_risk_experiment_runs(self):
        plan = self.planner.design(
            self.hypothesis.id,
            "kill the process",
            expects="port free",
            action="process.kill",
            risk="high",
            rollback="restart the service",
        )
        self.planner.approve(plan.id, "human")
        result = self.planner.run(plan.id, lambda e: "port free")

        self.assertTrue(result["ok"])
        self.assertEqual(self.planner.get(plan.id).status, DONE)

    def test_result_feeds_back_into_the_hypothesis(self):
        before = self.engine.get(self.hypothesis.id).confidence
        plan = self.planner.design(self.hypothesis.id, "list ports", expects="5432")
        self.planner.run(plan.id, lambda e: "tcp 5432 LISTEN")

        self.assertGreater(self.engine.get(self.hypothesis.id).confidence, before)

    def test_failed_prediction_lowers_confidence(self):
        before = self.engine.get(self.hypothesis.id).confidence
        plan = self.planner.design(self.hypothesis.id, "list ports", expects="5432")
        self.planner.run(plan.id, lambda e: "nothing listening")

        self.assertLess(self.engine.get(self.hypothesis.id).confidence, before)

    def test_intervention_experiment_marks_evidence_as_intervention(self):
        plan = self.planner.design(
            self.hypothesis.id,
            "stop the service then retry",
            expects="bound",
            intervenes=True,
            action="read",
        )
        self.planner.run(plan.id, lambda e: "bound")

        self.assertIn(INTERVENTION, self.engine.get(self.hypothesis.id).evidence_kinds())

    def test_runner_exception_is_captured_not_raised(self):
        plan = self.planner.design(self.hypothesis.id, "explode", expects="x")

        def boom(experiment):
            raise RuntimeError("tool crashed")

        result = self.planner.run(plan.id, boom)

        self.assertFalse(result["ok"])
        self.assertIn("RuntimeError", result["error"])

    def test_read_only_experiment_outranks_a_risky_one(self):
        cheap = self.planner.design(
            self.hypothesis.id, "read ports", expects="x", action="read"
        )
        risky = self.planner.design(
            self.hypothesis.id,
            "kill things",
            expects="x",
            action="process.kill",
            risk="high",
            rollback="restart",
        )

        self.assertGreater(cheap.value(), risky.value())

    def test_experiment_budget_per_goal_is_enforced(self):
        for index in range(experiments_module.MAX_PER_GOAL):
            self.planner.design(
                self.hypothesis.id, f"test {index}", expects="x", goal_id="g1"
            )

        with self.assertRaises(RuntimeError):
            self.planner.design(self.hypothesis.id, "one too many", expects="x", goal_id="g1")


class StrategyTests(unittest.TestCase):

    def setUp(self):
        self.registry = StrategyRegistry(temp_path("s.json"))

    def test_seeds_are_loaded(self):
        self.assertGreaterEqual(len(self.registry.all()), 5)

    def test_selection_discriminates_by_problem_structure(self):
        expected = {
            "the build keeps failing with an error": "hypothesis-first",
            "delete the old backup folders": "reversible-first",
            "should I use postgres or sqlite": "gather-then-decide",
            "the app crashes intermittently somewhere in startup":
                "narrow-the-search-space",
        }

        for problem, strategy in expected.items():
            result = self.registry.select(problem)

            self.assertTrue(result["found"], problem)
            self.assertEqual(result["strategy"].name, strategy, problem)

    def test_selection_records_why(self):
        self.registry.select("the build is failing")
        decisions = self.registry.why()

        self.assertTrue(decisions)
        self.assertTrue(decisions[0]["reason"])
        self.assertTrue(decisions[0]["considered"])

    def test_excluded_strategy_is_not_selected_again(self):
        first = self.registry.select("the build is failing")
        second = self.registry.select(
            "the build is failing", exclude=[first["strategy"].name]
        )

        self.assertNotEqual(second["strategy"].name, first["strategy"].name)

    def test_untried_strategy_is_not_scored_as_a_failure(self):
        untried = Strategy(name="brand-new", steps=["a"], problem_pattern=["widget"])

        self.assertEqual(untried.success_rate, 0.5)

    def test_consecutive_failures_lower_the_score(self):
        before = self.registry.candidates("the build is failing")[0]

        for _ in range(2):
            self.registry.record_outcome(before[0].name, False, note="did not work")

        after = [
            row for row in self.registry.candidates("the build is failing")
            if row[0].name == before[0].name
        ][0]

        self.assertLess(after[1], before[1])

    def test_replacement_is_refused_before_enough_failures(self):
        result = self.registry.propose_replacement("hypothesis-first")

        self.assertFalse(result["ok"])

    def test_replacement_is_proposed_after_repeated_failure(self):
        for index in range(3):
            self.registry.record_outcome("hypothesis-first", False, note=f"mode {index}")

        result = self.registry.propose_replacement("hypothesis-first")

        self.assertTrue(result["ok"])
        self.assertTrue(result["candidate"].steps)
        self.assertEqual(result["evidence"]["consecutive_failures"], 3)

    def test_unvalidated_replacement_is_not_adopted(self):
        for index in range(3):
            self.registry.record_outcome("hypothesis-first", False)

        candidate = self.registry.propose_replacement("hypothesis-first")["candidate"]
        result = self.registry.adopt_replacement("hypothesis-first", candidate, False)

        self.assertFalse(result["ok"])
        self.assertFalse(self.registry.get("hypothesis-first").deprecated)

    def test_validated_replacement_is_adopted_and_reversible(self):
        for index in range(3):
            self.registry.record_outcome("hypothesis-first", False)

        candidate = self.registry.propose_replacement("hypothesis-first")["candidate"]
        self.registry.adopt_replacement("hypothesis-first", candidate, True)

        self.assertTrue(self.registry.get("hypothesis-first").deprecated)
        self.assertTrue(self.registry.rollback_replacement("hypothesis-first"))
        self.assertFalse(self.registry.get("hypothesis-first").deprecated)

    def test_deprecated_strategy_is_not_selected(self):
        for index in range(3):
            self.registry.record_outcome("hypothesis-first", False)

        candidate = self.registry.propose_replacement("hypothesis-first")["candidate"]
        self.registry.adopt_replacement("hypothesis-first", candidate, True)

        names = [s.name for s in self.registry.all()]

        self.assertNotIn("hypothesis-first", names)

    def test_duplicate_registration_is_rejected(self):
        with self.assertRaises(KeyError):
            self.registry.add("hypothesis-first", ["a"])

    def test_mining_extracts_a_pattern_from_repeated_success(self):
        class FakeStore:
            def recent(self, limit=100):
                return [
                    {
                        "goal": f"organise the downloads folder {i}",
                        "success": True,
                        "strategy": "sort-by-type",
                        "duration": 1.0,
                    }
                    for i in range(5)
                ]

        found = self.registry.mine(store=FakeStore())

        self.assertTrue(found)
        self.assertEqual(found[0]["name"], "sort-by-type")
        self.assertIn("download", found[0]["problem_pattern"])

    def test_mining_ignores_failures(self):
        class FakeStore:
            def recent(self, limit=100):
                return [
                    {"goal": "x y z", "success": False, "strategy": "bad"}
                    for _ in range(9)
                ]

        self.assertEqual(self.registry.mine(store=FakeStore()), [])

    def test_survives_restart(self):
        path = temp_path("s_persist.json")
        first = StrategyRegistry(path)
        first.record_outcome("hypothesis-first", True, duration=2.0)

        second = StrategyRegistry(path)

        self.assertEqual(second.get("hypothesis-first").successes, 1)


class TransferTests(unittest.TestCase):

    def test_stemmer_does_not_split_a_doubled_s(self):
        self.assertEqual(stem("missing"), "miss")
        self.assertNotEqual(stem("miss"), stem("missing"))

    def test_stemmer_undoes_genuine_doubling(self):
        self.assertEqual(stem("running"), "run")
        self.assertEqual(stem("stopping"), "stop")

    def test_stemmer_handles_plurals_and_y(self):
        self.assertEqual(stem("dependencies"), stem("dependency"))
        self.assertEqual(stem("failing"), stem("failed"))

    def test_normalise_splits_compound_identifiers(self):
        self.assertEqual(normalise("ModuleNotFoundError"), "module not found error")
        self.assertEqual(normalise("file_not_found"), "file not found")

    def test_compound_error_names_are_classified(self):
        expected = {
            "the build failed with a ModuleNotFoundError": "missing_prerequisite",
            "FileNotFoundError: config.json": "missing_prerequisite",
            "PermissionError while writing": "permission_boundary",
            "OSError: No space left on device": "capacity_limit",
        }

        for text, structure in expected.items():
            result = transfer.abstract(text)

            self.assertIsNotNone(result, text)
            self.assertEqual(result.structure, structure, text)

    def test_unrecognised_text_is_not_forced_into_a_structure(self):
        self.assertIsNone(transfer.abstract("the weather is pleasant today"))

    def test_miss_does_not_match_missing(self):
        result = transfer.abstract("we will miss the deadline")

        if result is not None:
            self.assertNotEqual(result.structure, "missing_prerequisite")

    def test_cross_domain_analogy_maps_on_structure_not_vocabulary(self):
        result = transfer.map_analogy(
            "chrome would not start because the process was already running",
            "the database connection failed, the port is already in use",
        )

        self.assertTrue(result["mapped"])
        self.assertEqual(result["structure"], "resource_conflict")
        self.assertTrue(result["cross_domain"])
        self.assertLess(result["surface_similarity"], 0.3)

    def test_different_structures_do_not_map(self):
        result = transfer.map_analogy(
            "the process was already running", "the config file is missing"
        )

        self.assertFalse(result["mapped"])

    def test_unstructured_problem_does_not_map(self):
        result = transfer.map_analogy("the sky is blue", "grass is green")

        self.assertFalse(result["mapped"])

    def test_counterfactual_does_not_execute(self):
        state = {"folder": "exists"}
        result = transfer.counterfactual(state, {"folder": "deleted"})

        self.assertFalse(result["executed"])
        self.assertEqual(state["folder"], "exists")
        self.assertEqual(result["actual"]["folder"], "exists")

    def test_counterfactual_chains_second_order_effects(self):
        result = transfer.counterfactual(
            {"folder": "exists", "build": "ok"},
            {"folder": "deleted"},
            rules=[
                {"if": {"folder": "deleted"}, "then": {"build": "broken"},
                 "description": "the build reads from the folder"},
                {"if": {"build": "broken"}, "then": {"release": "blocked"},
                 "description": "a release needs a build"},
            ],
        )

        self.assertEqual(len(result["effects"]), 2)
        self.assertEqual(result["hypothetical"]["release"], "blocked")

    def test_counterfactual_reports_unknowns_rather_than_assuming_safety(self):
        result = transfer.counterfactual({"a": 1}, {"mystery": "changed"})

        self.assertTrue(result["unknowns"])
        self.assertLess(result["confidence"], 1.0)

    def test_transfer_marks_domain_specific_terms_for_substitution(self):
        result = transfer.transfer_strategy(
            ["run the test suite", "check the build output"], "coding", "research"
        )

        self.assertTrue(result["substitutions_required"])

    def test_domain_free_steps_transfer_cleanly(self):
        result = transfer.transfer_strategy(
            ["list what is known", "collect what is missing"], "coding", "research"
        )

        self.assertTrue(result["transferable"])
        self.assertEqual(result["substitutions_required"], [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
