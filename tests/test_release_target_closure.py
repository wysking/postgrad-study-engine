"""Fictional target-aware closure through ordinary mobile requests."""

from scripts.contracts import load_jsonl
from tests.fictional_release_vault import FictionalMobileVault, START, UNIT


class TargetClosureTests(FictionalMobileVault):
    def completion(self, targets, *, expected_open, expected_independent=0, **fields):
        self.register(targets)
        diagnosis = {
            "schema_version": "1.0", "event_id": "fictional-diagnosis",
            "timestamp": START, "event_type": "diagnosis", "subject": "math",
            "unit_ids": [UNIT], "diagnosis": {
                "diagnosis_id": "fictional-episode", "question_id": "fictional-initial",
                "status": "confirmed", "generated_by": "joint",
                "first_divergence": "Fictional omitted condition in a clear draft.",
                "confirmation_method": "draft_check",
                "learner_verdict": "Fictional learner checked the written step.",
            },
        }
        self.call("record_diagnosis", {"event": diagnosis})
        event = self.attempt(parent_diagnosis_id="fictional-episode", **fields)
        self.call("record_attempt", {"event": event})
        state = self.state()
        targeted = [t for t in state["review_queue"] if t["task_type"] == "targeted_variant"]
        self.assertEqual(bool(targeted), expected_open)
        self.assertEqual(state["units"][UNIT]["clean_independent_correct"], expected_independent)
        self.assertEqual(state["diagnoses"]["fictional-episode"]["status"], "confirmed")
        # Closing work does not edit either historical observation or diagnosis.
        self.assertEqual(load_jsonl(self.root / "events/learning_events.jsonl"), [diagnosis, event])
        if expected_independent:
            self.assertIn("review", [t["task_type"] for t in state["review_queue"]])
            self.assertNotIn("diagnostic", [t["task_type"] for t in state["review_queue"]])
        return state["units"][UNIT]

    def test_recall_cannot_close_transfer_only_work(self):
        self.completion(["transfer"], activity="recall", mode="recalled", expected_open=True)

    def test_recall_cannot_close_timed_only_work(self):
        self.completion(["timed"], activity="recall", mode="recalled", expected_open=True)

    def test_unmeasured_timed_work_stays_open_without_discarding_independent_success(self):
        unit = self.completion(["timed"], activity="timed_practice", expected_open=True,
                               expected_independent=1)
        self.assertEqual(unit["qualified_positive_counts"]["timed"], 0)

    def test_ordinary_solving_does_not_substitute_for_transfer(self):
        self.completion(["transfer"], expected_open=True, expected_independent=1)

    def test_delayed_only_work_requires_observed_delay(self):
        self.completion(["delayed"], activity="recall", mode="recalled", expected_open=True)

    def test_recall_only_work_can_close_without_solving_credit(self):
        self.completion(["recall", "delayed"], activity="recall", mode="recalled", expected_open=False)

    def test_one_supported_solving_target_can_close_immediate_work(self):
        unit = self.completion(["independent", "transfer", "timed"], expected_open=False,
                               expected_independent=1)
        self.assertEqual(unit["qualified_positive_counts"]["transfer"], 0)
        self.assertEqual(unit["qualified_positive_counts"]["timed"], 0)
        self.assertIsNone(unit["mastery_overall"])

    def test_independent_variant_can_close_transfer_work(self):
        self.completion(["transfer"], activity="variant", expected_open=False, expected_independent=1)

    def test_measured_independent_timed_work_can_close(self):
        self.completion(["timed"], activity="timed_practice", time_minutes=8,
                        expected_open=False, expected_independent=1)
