"""Fictional closure tests extending the already-covered PR #1 cases."""
from __future__ import annotations

import unittest

from scripts.contracts import parse_datetime
from scripts.reducer import rebuild_state
from tests.test_error_loop import UNIT, attempt_event, diagnosis_event


class DiagnosisClosureTests(unittest.TestCase):
    def linked(self, **fields):
        return attempt_event("fictional-linked", "2026-08-10T09:30:00Z",
                             parent_diagnosis_id="diag-limit-001", **fields)

    def test_same_unit_explanation_cannot_complete_a_solving_diagnosis(self):
        diag = diagnosis_event("fictional-diag", "2026-08-10T09:00:00Z", "confirmed")
        state = rebuild_state([diag, self.linked(activity="explain")])
        targeted = [task for task in state["review_queue"] if task["task_type"] == "targeted_variant"]
        self.assertEqual(len(targeted), 1)
        self.assertEqual(targeted[0]["diagnosis_id"], "diag-limit-001")
        self.assertEqual(state["units"][UNIT]["clean_independent_correct"], 0)

    def test_uncertain_assisted_and_unverified_linked_success_leave_diagnosis_open(self):
        for fields in [{"answer_mode": "uncertain"}, {"process_check": "not_available"},
                       {"process_check": "suspicious"},
                       {"answer_mode": "assisted", "assistance_level": 1}]:
            with self.subTest(fields=fields):
                diag = diagnosis_event("fictional-diag", "2026-08-10T09:00:00Z", "confirmed")
                state = rebuild_state([diag, self.linked(**fields)])
                self.assertIn("targeted_variant", [task["task_type"] for task in state["review_queue"]])

    def test_unknown_parent_keeps_real_success_but_reports_unmatched_reference(self):
        item = self.linked()
        state = rebuild_state([item])
        self.assertEqual(state["units"][UNIT]["clean_independent_correct"], 1)
        self.assertTrue(any("unmatched parent diagnosis" in warning for warning in state["warnings"]))
        self.assertEqual(state["diagnoses"], {})

    def test_mismatched_parent_unit_does_not_close_required_work(self):
        diag = diagnosis_event("fictional-diag", "2026-08-10T09:00:00Z", "confirmed")
        item = self.linked()
        item["unit_ids"] = ["math.fictional.other_unit"]
        state = rebuild_state([diag, item])
        targeted = [task for task in state["review_queue"] if task["task_type"] == "targeted_variant"]
        self.assertEqual([task["unit_id"] for task in targeted], [UNIT])
        self.assertTrue(any("unmatched parent diagnosis" in warning for warning in state["warnings"]))

    def test_valid_linked_solving_success_closes_only_immediate_work(self):
        diag = diagnosis_event("fictional-diag", "2026-08-10T09:00:00Z", "confirmed")
        state = rebuild_state([diag, self.linked(activity="variant")])
        self.assertNotIn("targeted_variant", [task["task_type"] for task in state["review_queue"]])
        self.assertIn("review", [task["task_type"] for task in state["review_queue"]])
        self.assertEqual(state["diagnoses"]["diag-limit-001"]["status"], "confirmed")

    def test_later_failure_is_not_removed_by_a_forward_evidence_reference(self):
        diag = diagnosis_event("fictional-diag", "2026-08-10T09:00:00Z", "hypothesized")
        diag["diagnosis"]["evidence_refs"] = ["fictional-later-failure"]
        later = attempt_event("fictional-later-failure", "2026-08-10T09:30:00Z", result="incorrect")
        state = rebuild_state([diag, later])
        correction = [task for task in state["review_queue"] if task["task_type"] == "correction"]
        self.assertEqual([task["source_event_id"] for task in correction], ["fictional-later-failure"])

    def test_recommendation_cannot_defer_current_error_or_uncertain_result(self):
        for fields in [{"result": "incorrect"}, {"result": "partial"}, {"result": "unanswered"},
                       {"answer_mode": "guess"}, {"answer_mode": "uncertain"},
                       {"process_check": "not_available"}]:
            with self.subTest(fields=fields):
                item = attempt_event("fictional-urgent", "2026-08-10T09:00:00Z", **fields)
                item["recommended_review_at"] = "2030-01-01T00:00:00Z"
                state = rebuild_state([item])
                self.assertEqual(parse_datetime(state["review_queue"][0]["due_at"]),
                                 parse_datetime(item["timestamp"]))

    def test_assistance_still_requires_next_day_check_despite_late_recommendation(self):
        item = attempt_event("fictional-assisted", "2026-08-10T09:00:00Z",
                             answer_mode="assisted", assistance_level=1)
        item["recommended_review_at"] = "2030-01-01T00:00:00Z"
        task = rebuild_state([item])["review_queue"][0]
        self.assertEqual(task["task_type"], "diagnostic")
        self.assertEqual(task["due_at"], "2026-08-11T09:00:00Z")

    def test_valid_success_can_use_review_recommendation_without_past_due_date(self):
        item = attempt_event("fictional-success", "2026-08-10T09:00:00Z")
        item["recommended_review_at"] = "2026-08-17T09:00:00Z"
        self.assertEqual(rebuild_state([item])["review_queue"][0]["due_at"], item["recommended_review_at"])
        item["recommended_review_at"] = "2026-08-09T09:00:00Z"
        self.assertEqual(rebuild_state([item])["review_queue"][0]["due_at"], item["timestamp"])

    def test_recall_only_unit_can_complete_retrieval_without_independent_solving_credit(self):
        registry = {UNIT: {"schema_version": "1.0", "unit_id": UNIT, "subject": "math",
                          "title": "Fictional definition recall", "evidence_targets": ["recall", "delayed"]}}
        diag = diagnosis_event("fictional-diag", "2026-08-10T09:00:00Z", "confirmed")
        item = self.linked(activity="review", answer_mode="recalled", delayed_days=3)
        state = rebuild_state([diag, item], registry)
        self.assertNotIn("targeted_variant", [task["task_type"] for task in state["review_queue"]])
        self.assertIn("review", [task["task_type"] for task in state["review_queue"]])
        self.assertEqual(state["units"][UNIT]["clean_independent_correct"], 0)
        self.assertGreater(state["units"][UNIT]["mastery"]["recall"], 0.5)


if __name__ == "__main__":
    unittest.main()
