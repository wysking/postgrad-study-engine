"""Fictional regressions for due dates, overlapping checks and known dependencies."""

from __future__ import annotations

import copy
import unittest

from scripts.contracts import ContractError, load_json
from scripts.schedule_global import DEFAULT_CONFIG
from scripts.scheduler import build_schedule
from tests.test_scheduler import candidate, empty_state


AS_OF = "2026-08-10T00:00:00Z"
UNIT = "math.sample.unit"
PREREQUISITE = "math.sample.foundation"


def queue_task(task_id, kind, **overrides):
    return candidate(task_id, "math", 10, **{
        "task_type": kind, "due_at": AS_OF, "diagnosis_id": None,
        "source_event_id": "fictional-source", "error_tags": [], **overrides,
    })


class SchedulerEligibilityTests(unittest.TestCase):
    def setUp(self):
        self.config = load_json(DEFAULT_CONFIG)
        self.request = {"schema_version": "1.0", "available_minutes": 30,
                        "as_of": AS_OF, "phase_subjects": ["math"]}

    def schedule(self, state=None, **overrides):
        return build_schedule(state or empty_state(), {**self.request, **overrides}, self.config)

    def test_derived_future_review_is_excluded_and_queue_is_unchanged(self):
        state = empty_state()
        state["review_queue"] = [queue_task("future", "review", due_at="2026-08-11T00:00:00Z")]
        before = copy.deepcopy(state)
        result = self.schedule(state)
        self.assertEqual(result["selected_tasks"], [])
        self.assertEqual(result["excluded_candidates"], [{"task_id": "future", "reason": "review_not_due"}])
        self.assertEqual(state, before)

    def test_external_future_review_obeys_same_due_gate(self):
        result = self.schedule(candidates=[queue_task("external", "review", due_at="2026-08-10T00:00:01Z")])
        self.assertEqual(result["selected_tasks"], [])

    def test_review_due_at_exact_instant_in_another_timezone_is_eligible(self):
        result = self.schedule(candidates=[queue_task("due", "review", due_at="2026-08-10T08:00:00+08:00")])
        self.assertEqual([task["task_id"] for task in result["selected_tasks"]], ["due"])

    def test_explicit_early_practice_does_not_become_a_delayed_review(self):
        result = self.schedule(candidates=[queue_task("practice", "practice", due_at="2026-08-11T00:00:00Z")])
        self.assertEqual(result["selected_tasks"][0]["task_type"], "practice")

    def test_generic_correction_and_diagnostic_share_one_session_slot(self):
        state = empty_state()
        state["review_queue"] = [queue_task("correction", "correction"), queue_task("diagnostic", "diagnostic")]
        before = copy.deepcopy(state)
        result = self.schedule(state)
        self.assertEqual(len(result["selected_tasks"]), 1)
        self.assertEqual(result["excluded_candidates"][0]["reason"], "overlapping_unit_check")
        self.assertEqual(state, before)

    def test_overlap_constraint_keeps_shorter_alternative_for_budget_selection(self):
        tasks = [
            candidate("long", "math", 30, task_type="correction", expected_score_gain=0.9),
            candidate("short", "math", 10, task_type="diagnostic"),
            candidate("other", "math", 20, unit_id="math.sample.other", expected_score_gain=0.9),
        ]
        result = self.schedule(candidates=tasks)
        self.assertEqual({task["task_id"] for task in result["selected_tasks"]}, {"short", "other"})

    def test_distinct_diagnoses_are_not_assumed_to_test_the_same_gap(self):
        result = self.schedule(candidates=[
            queue_task("first", "diagnostic", diagnosis_id="fictional-first"),
            queue_task("second", "diagnostic", diagnosis_id="fictional-second"),
        ])
        self.assertEqual(len(result["selected_tasks"]), 2)

    def test_overlap_selection_is_deterministic_for_input_order(self):
        tasks = [queue_task("correction", "correction"), queue_task("diagnostic", "diagnostic")]
        self.assertEqual(self.schedule(candidates=tasks), self.schedule(candidates=list(reversed(tasks))))

    def dependent_state(self, mastery):
        state = empty_state()
        state["units"] = {
            UNIT: {"subject": "math", "prerequisites": [PREREQUISITE], "attempts": {"total": 1}, "mastery_overall": None},
            PREREQUISITE: {"subject": "math", "prerequisites": [], "attempts": {"total": 1}, "mastery_overall": mastery},
        }
        return state

    def test_external_learning_cannot_override_unknown_registered_prerequisite(self):
        result = self.schedule(self.dependent_state(None), candidates=[candidate("external", "math", task_type="learn", prerequisite_ready=True)])
        self.assertNotIn("external", [task["task_id"] for task in result["selected_tasks"]])
        self.assertIn({"task_id": "external", "reason": "prerequisite_not_ready"}, result["excluded_candidates"])

    def test_external_learning_without_readiness_flag_still_checks_registry(self):
        task = candidate("external", "math", task_type="learn")
        task.pop("prerequisite_ready")
        result = self.schedule(self.dependent_state(None), candidates=[task])
        self.assertNotIn("external", [item["task_id"] for item in result["selected_tasks"]])

    def test_ready_registered_prerequisite_allows_external_learning(self):
        result = self.schedule(self.dependent_state(self.config["prerequisite_threshold"]), candidates=[candidate("external", "math", task_type="learn")])
        self.assertIn("external", [task["task_id"] for task in result["selected_tasks"]])

    def test_missing_registered_prerequisite_is_not_treated_as_ready(self):
        state = self.dependent_state(None)
        state["units"].pop(PREREQUISITE)
        result = self.schedule(state, candidates=[candidate("external", "math", task_type="learn")])
        self.assertNotIn("external", [task["task_id"] for task in result["selected_tasks"]])

    def test_remediation_can_probe_a_unit_with_unknown_prerequisites(self):
        result = self.schedule(self.dependent_state(None), candidates=[queue_task("repair", "diagnostic")])
        self.assertIn("repair", [task["task_id"] for task in result["selected_tasks"]])

    def test_invalid_unit_reference_reports_a_contract_error(self):
        with self.assertRaisesRegex(ContractError, "unit_id"):
            self.schedule(candidates=[candidate("invalid", "math", unit_id=[UNIT])])

    def test_old_config_label_does_not_hide_changed_scheduler_semantics(self):
        self.config["model_version"] = "constrained-priority-0.1"
        result = self.schedule(candidates=[candidate("fictional", "math")])
        self.assertEqual(result["model_version"], "constrained-priority-0.2")
        self.assertEqual(result["config_model_version"], "constrained-priority-0.1")


if __name__ == "__main__":
    unittest.main()
