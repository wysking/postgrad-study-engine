"""Fictional controls for model qualification, fitting and temporal leakage."""

import copy
import json
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from scripts.contracts import ContractError
from scripts.learning_models import (evaluate_memory, fit_half_life, fit_models,
                                     memory_data, recall_prediction)
from scripts.reducer import load_units

ROOT = Path(__file__).resolve().parents[1]
COURSE = json.loads((ROOT / "examples/courses/limits-and-recall.json").read_text(encoding="utf-8"))
EVENTS = json.loads((ROOT / "examples/courses/fictional-14-days.json").read_text(encoding="utf-8"))["events"]
AS_OF = datetime(2026, 8, 15, 9, tzinfo=timezone.utc)
MEMORY = "english.vocab.ephemeral"


class LearningModelTests(unittest.TestCase):
    def model(self, events=None, cutoff=AS_OF, learner="fictional-a"):
        return fit_models(EVENTS if events is None else events, COURSE["units"], cutoff, learner)

    def test_zero_samples_runs_without_inventing_prediction(self):
        m = self.model([])
        x = m["memory"][MEMORY]
        self.assertEqual(x["status"], "prior_only")
        self.assertAlmostEqual(x["half_life_days"], 3)
        self.assertIsNone(x["predicted_recall"])
        self.assertEqual(m["sample_audit"]["included"], [])

    def test_real_fit_moves_both_directions_and_is_bounded(self):
        successes = [{"elapsed_days": 7, "recalled": 1, "event_id": str(i)} for i in range(20)]
        failures = [{**s, "recalled": 0} for s in successes]
        self.assertGreater(fit_half_life(successes)["half_life_days"], 3)
        self.assertLess(fit_half_life(failures)["half_life_days"], 3)
        lo, hi = fit_half_life(successes)["model_interval_90_days"]
        self.assertLess(lo, hi)

    def test_curve_has_half_life_identity_and_decays(self):
        self.assertAlmostEqual(recall_prediction(4, 4), 0.5)
        self.assertEqual(recall_prediction(0, 4), 1)
        self.assertGreater(recall_prediction(1, 4), recall_prediction(2, 4))
        for value in (-1, float("nan"), float("inf")):
            with self.assertRaises(ContractError):
                recall_prediction(value, 4)

    def test_solving_is_not_a_recall_sample(self):
        m = self.model()
        self.assertNotIn("math.limit.equivalence_solve", m["memory"])
        self.assertTrue(all(s["unit_id"] in m["memory"] for s in m["sample_audit"]["included"]))
        self.assertEqual(len(m["sample_audit"]["included"]), 6)

    def test_assisted_observation_breaks_anchor_without_granting_sample(self):
        events = copy.deepcopy([e for e in EVENTS if e["unit_ids"] == [MEMORY]])
        events[1]["attempt"].update(answer_mode="assisted", assistance_level=1)
        data = memory_data(events, load_units(COURSE["units"]), AS_OF)
        self.assertEqual(len(data["samples"]), 1)
        self.assertEqual(data["samples"][0]["event_id"], events[-1]["event_id"])

    def test_missing_delay_does_not_become_observed_delay(self):
        events = copy.deepcopy([e for e in EVENTS if e["unit_ids"] == [MEMORY]])
        for e in events:
            e["attempt"].pop("delayed_days", None)
        self.assertEqual(self.model(events)["sample_audit"]["included"], [])

    def test_conflicting_delay_and_multi_unit_events_are_excluded(self):
        events = copy.deepcopy([e for e in EVENTS if e["unit_ids"] == [MEMORY]])
        events[1]["attempt"]["delayed_days"] = 30
        events[2]["unit_ids"].append("math.limit.standard_recall")
        m = self.model(events)
        reasons = {x["reason"] for x in m["sample_audit"]["excluded"]}
        self.assertIn("delay_conflicts_with_anchor_timestamps", reasons)
        self.assertIn("multiple_units_are_not_independent_retrieval_samples", reasons)
        self.assertEqual(m["sample_audit"]["included"], [])

    def test_future_outcomes_do_not_change_past_fit_hash_or_evaluation(self):
        cutoff = datetime(2026, 8, 8, 9, tzinfo=timezone.utc)
        early = [e for e in EVENTS if datetime.fromisoformat(e["timestamp"].replace("Z", "+00:00")) <= cutoff]
        self.assertEqual(self.model(EVENTS, cutoff), self.model(early, cutoff))
        self.assertEqual(evaluate_memory(EVENTS, COURSE["units"], cutoff),
                         evaluate_memory(early, COURSE["units"], cutoff))

    def test_individuals_are_isolated_and_fitting_is_deterministic(self):
        original = copy.deepcopy(EVENTS)
        a, b = self.model(), self.model([], learner="fictional-b")
        self.assertNotEqual(a["learner_id"], b["learner_id"])
        self.assertNotEqual(a["model_id"], b["model_id"])
        self.assertEqual(self.model(), a)
        self.assertEqual(EVENTS, original)

    def test_skill_risk_preserves_prior_and_excludes_assisted_success(self):
        risk = self.model()["skill_risks"]
        self.assertEqual(risk["math.limit.mixed"]["status"], "prior_only")
        solve = risk["math.limit.equivalence_solve"]
        self.assertEqual(solve["sample_count"], 4)
        self.assertEqual(solve["incorrect"], 1)
        self.assertNotIn("fictional-day-3", solve["source_event_ids"])

    def test_prequential_evaluation_does_not_train_on_the_scored_outcome(self):
        report = evaluate_memory(EVENTS, COURSE["units"], AS_OF)
        seen = {}
        for p in report["predictions"]:
            self.assertEqual(p["fit_samples_before_prediction"], seen.get(p["unit_id"], 0))
            seen[p["unit_id"]] = seen.get(p["unit_id"], 0) + 1
        self.assertEqual(report["sample_count"], 6)
        self.assertGreaterEqual(report["metrics"]["model"]["brier"], 0)
        self.assertLessEqual(report["metrics"]["model"]["brier"], 1)
        self.assertEqual(report["validation_status"], "descriptive_only_not_validated")

    def test_empty_evaluation_has_no_fabricated_metric(self):
        r = evaluate_memory([], COURSE["units"], AS_OF)
        self.assertEqual(r["sample_count"], 0)
        self.assertIsNone(r["metrics"]["model"]["brier"])

    def test_same_timestamp_outcomes_are_predicted_before_any_group_update(self):
        events = copy.deepcopy(EVENTS)
        # Different cards at the same instant are not extra training for one another.
        r = evaluate_memory(events, COURSE["units"], AS_OF)
        first = [p for p in r["predictions"] if p["timestamp"] == "2026-08-04T09:00:00Z"]
        self.assertEqual([p["fit_samples_before_prediction"] for p in first], [0, 0])

    def test_naive_cutoff_and_duplicate_events_fail(self):
        with self.assertRaises(ContractError):
            self.model([], AS_OF.replace(tzinfo=None))
        with self.assertRaises(ContractError):
            self.model(EVENTS + [EVENTS[0]])


if __name__ == "__main__":
    unittest.main()
