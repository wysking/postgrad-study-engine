"""Fictional regressions for evidence qualification; never import into a Vault."""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from scripts.contracts import ContractError, validate_learning_event
from scripts.reducer import rebuild_state
from tests.test_error_loop import UNIT, attempt_event


class EvidenceQualificationTests(unittest.TestCase):
    def attempt(self, identifier="fictional-evidence", **fields):
        return attempt_event(identifier, "2026-08-10T09:00:00Z", **fields)

    def test_assisted_flagged_correct_keeps_observation_without_independent_gain(self):
        for fields in [
            {"answer_mode": "assisted", "assistance_level": 1},
            {"answer_mode": "assisted", "assistance_level": 5},
            {"answer_mode": "guess"},
            {"answer_mode": "uncertain"},
            {"answer_mode": "recalled"},
            {"process_check": "suspicious"},
            {"process_check": "not_available"},
        ]:
            with self.subTest(fields=fields):
                state = rebuild_state([self.attempt(**fields)])
                unit = state["units"][UNIT]
                self.assertEqual(unit["mastery"]["independent"], 0.5)
                self.assertEqual(unit["qualified_positive_counts"]["independent"], 0)
                self.assertEqual(unit["attempts"]["correct"], 1)
                self.assertEqual(unit["flagged_correct"], 1)
                self.assertEqual(unit["clean_independent_correct"], 0)
                self.assertIsNone(unit["mastery_overall"])
                self.assertNotIn("review", [task["task_type"] for task in state["review_queue"]])

    def test_wrong_and_partial_evidence_is_retained_under_both_assistance_conditions(self):
        for result in ["incorrect", "partial", "unanswered"]:
            for mode, assistance in [("independent", 0), ("assisted", 3)]:
                with self.subTest(result=result, mode=mode):
                    state = rebuild_state([self.attempt(result=result, answer_mode=mode,
                                                        assistance_level=assistance)])
                    unit = state["units"][UNIT]
                    self.assertLess(unit["mastery"]["independent"], 0.5)
                    self.assertEqual(unit["attempts"][result], 1)
                    self.assertEqual(unit["qualified_positive_counts"]["independent"], 0)
                    self.assertEqual(state["review_queue"][0]["task_type"], "correction")

    def test_direct_rebuild_rejects_hidden_assistance(self):
        with self.assertRaisesRegex(ContractError, "independent attempt"):
            rebuild_state([self.attempt(assistance_level=1)])

    def test_schema_and_runtime_agree_independent_requires_zero_assistance(self):
        schema = json.loads((Path(__file__).parents[1] / "schemas/learning_event.schema.json").read_text())
        rule = next(rule for rule in schema["allOf"] if
                    "answer_mode" in rule.get("if", {}).get("properties", {}).get("attempt", {}).get("properties", {}))
        self.assertEqual(rule["then"]["properties"]["attempt"]["properties"]["assistance_level"]["const"], 0)
        for level in [1, 5, True, False]:
            with self.subTest(level=level):
                with self.assertRaises(ContractError):
                    validate_learning_event(self.attempt(assistance_level=level))

    def test_variant_supplies_two_dimensions_but_remains_one_attempt(self):
        state = rebuild_state([self.attempt(activity="variant")])
        unit = state["units"][UNIT]
        self.assertGreater(unit["mastery"]["independent"], 0.5)
        self.assertGreater(unit["mastery"]["transfer"], 0.5)
        self.assertEqual(unit["attempts"]["total"], 1)
        self.assertEqual(unit["clean_independent_correct"], 1)

    def test_supported_explanation_keeps_value_without_becoming_independent_solving(self):
        state = rebuild_state([self.attempt(activity="explain", answer_mode="assisted", assistance_level=1)])
        unit = state["units"][UNIT]
        self.assertGreater(unit["mastery"]["comprehension"], 0.5)
        self.assertNotIn("independent", unit["mastery"])
        self.assertEqual(unit["clean_independent_correct"], 0)
        self.assertEqual(unit["assisted_attempts"], 1)
        self.assertIsNone(unit["mastery_overall"])

    def test_assisted_delayed_and_timed_success_cannot_promote_those_dimensions(self):
        state = rebuild_state([self.attempt(activity="timed_practice", answer_mode="assisted",
                                            assistance_level=1, delayed_days=7)])
        unit = state["units"][UNIT]
        for dimension in ["independent", "delayed", "timed"]:
            self.assertEqual(unit["mastery"][dimension], 0.5)
            self.assertEqual(unit["qualified_positive_counts"][dimension], 0)

    def test_timed_activity_without_measured_time_is_not_speed_evidence(self):
        item = self.attempt(activity="timed_practice")
        del item["attempt"]["time_minutes"]
        unit = rebuild_state([item])["units"][UNIT]
        self.assertEqual(unit["mastery"]["timed"], 0.5)
        self.assertGreater(unit["mastery"]["independent"], 0.5)

    def test_one_dimension_does_not_stand_in_for_missing_coverage(self):
        unit = rebuild_state([self.attempt()])["units"][UNIT]
        self.assertIsNone(unit["mastery_overall"])
        self.assertIn("transfer", unit["evidence_coverage"]["missing_targets"])
        self.assertFalse(unit["evidence_coverage"]["sufficient_for_overall"])

    def test_independent_overall_requires_two_distinct_questions_even_for_one_target(self):
        registry = {UNIT: {"schema_version": "1.0", "unit_id": UNIT,
                          "subject": "math", "title": "Fictional narrow unit",
                          "evidence_targets": ["independent"]}}
        first = self.attempt("fictional-first")
        same = self.attempt("fictional-repeat")
        different = self.attempt("fictional-new-question", question_id="fictional-other-question")
        self.assertIsNone(rebuild_state([first], registry)["units"][UNIT]["mastery_overall"])
        self.assertIsNone(rebuild_state([first, same], registry)["units"][UNIT]["mastery_overall"])
        sufficient = rebuild_state([first, different], registry)["units"][UNIT]
        self.assertIsNotNone(sufficient["mastery_overall"])
        self.assertEqual(sufficient["evidence_coverage"]["independent_questions"], 2)

    def test_two_assisted_successes_do_not_satisfy_a_comprehension_only_overall(self):
        registry = {UNIT: {"schema_version": "1.0", "unit_id": UNIT, "subject": "math",
                          "title": "Fictional explanation", "evidence_targets": ["comprehension"]}}
        items = [self.attempt(f"fictional-supported-{i}", activity="explain",
                             answer_mode="assisted", assistance_level=1) for i in range(2)]
        unit = rebuild_state(items, registry)["units"][UNIT]
        self.assertGreater(unit["mastery"]["comprehension"], 0.5)
        self.assertIsNone(unit["mastery_overall"])

    def test_boolean_delay_is_not_an_integer_review_interval(self):
        with self.assertRaises(ContractError):
            validate_learning_event(self.attempt(delayed_days=True))


if __name__ == "__main__":
    unittest.main()
