from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.contracts import ContractError, load_json
from scripts.schedule_global import DEFAULT_CONFIG, main as schedule_main
from scripts.scheduler import build_schedule


def empty_state():
    return {
        "schema_version": "1.0",
        "model_version": "heuristic-evidence-0.1",
        "generated_at": "2026-08-10T00:00:00Z",
        "event_count": 0,
        "units": {},
        "diagnoses": {},
        "error_patterns": {},
        "review_queue": [],
        "warnings": [],
    }


def candidate(task_id: str, subject: str, minutes: int = 30, **overrides):
    return {
        "task_id": task_id,
        "task_type": "practice",
        "subject": subject,
        "unit_id": f"{subject}.sample.unit",
        "activity": "solve",
        "estimated_minutes": minutes,
        "expected_score_gain": 0.5,
        "forgetting_risk": 0.3,
        "information_gain": 0.4,
        "transfer_value": 0.4,
        "urgency": 0.3,
        "error_recurrence": 0.0,
        "fatigue_cost": 0.2,
        "prerequisite_ready": True,
        "reason": "test candidate",
        **overrides,
    }


class SchedulerTests(unittest.TestCase):
    def setUp(self):
        self.config = load_json(DEFAULT_CONFIG)

    def test_budget_phase_prerequisite_and_subject_cap_are_enforced(self):
        request = {
            "schema_version": "1.0",
            "available_minutes": 60,
            "as_of": "2026-08-10T08:00:00+08:00",
            "max_subject_share": 0.5,
            "phase_subjects": ["math", "english", "materials"],
            "candidates": [
                candidate("math-high", "math", expected_score_gain=0.9),
                candidate("math-second", "math", expected_score_gain=0.8),
                candidate("english", "english", expected_score_gain=0.6),
                candidate("materials-blocked", "materials", expected_score_gain=1.0, prerequisite_ready=False),
                candidate("politics-out-of-phase", "politics", expected_score_gain=1.0),
            ],
        }
        result = build_schedule(empty_state(), request, self.config)
        selected = {item["task_id"] for item in result["selected_tasks"]}
        self.assertEqual(result["scheduled_minutes"], 60)
        self.assertEqual(selected, {"math-high", "english"})
        self.assertEqual(result["subject_minutes"], {"english": 30, "math": 30})
        excluded = {item["task_id"]: item["reason"] for item in result["excluded_candidates"]}
        self.assertEqual(excluded["materials-blocked"], "prerequisite_not_ready")
        self.assertEqual(excluded["politics-out-of-phase"], "subject_not_in_phase")

    def test_as_of_is_required_for_reproducible_due_dates(self):
        request = {
            "schema_version": "1.0",
            "available_minutes": 30,
            "phase_subjects": ["math"],
            "candidates": [candidate("math", "math")],
        }
        with self.assertRaisesRegex(ContractError, "requires as_of"):
            build_schedule(empty_state(), request, self.config)

    def test_due_diagnostic_beats_optional_learning_task(self):
        state = empty_state()
        state["units"] = {
            "math.limit.conditions": {
                "unit_id": "math.limit.conditions",
                "subject": "math",
                "exam_weight": 0.8,
                "estimated_minutes": 20,
                "mastery_overall": 0.4,
                "prerequisites": [],
                "attempts": {"total": 1},
            }
        }
        state["error_patterns"] = {"condition-check": {"count": 3}}
        state["review_queue"] = [{
            "task_id": "diagnostic:math.limit.conditions",
            "task_type": "diagnostic",
            "subject": "math",
            "unit_id": "math.limit.conditions",
            "activity": "solve",
            "due_at": "2026-08-01T00:00:00Z",
            "estimated_minutes": 20,
            "reason": "guessed correct",
            "source_event_id": "e1",
            "diagnosis_id": None,
            "error_tags": ["condition-check"],
        }]
        request = {
            "schema_version": "1.0",
            "available_minutes": 20,
            "as_of": "2026-08-10T00:00:00Z",
            "phase_subjects": ["math"],
            "candidates": [candidate(
                "optional-new",
                "math",
                20,
                task_type="learn",
                activity="learn",
                expected_score_gain=0.8,
                information_gain=0.1,
                forgetting_risk=0.0,
                urgency=0.0,
            )],
        }
        result = build_schedule(state, request, self.config)
        self.assertEqual([item["task_id"] for item in result["selected_tasks"]], ["diagnostic:math.limit.conditions"])
        breakdown = result["selected_tasks"][0]["score_breakdown"]
        self.assertGreater(breakdown["components"]["error_recurrence"], 0)

    def test_scheduler_is_deterministic_for_candidate_order(self):
        items = [
            candidate("math", "math", 25),
            candidate("english", "english", 25),
            candidate("materials", "materials", 25),
        ]
        base = {
            "schema_version": "1.0",
            "available_minutes": 50,
            "as_of": "2026-08-10T00:00:00Z",
            "max_subject_share": 0.6,
            "phase_subjects": ["math", "english", "materials"],
        }
        first = build_schedule(empty_state(), {**base, "candidates": items}, self.config)
        second = build_schedule(empty_state(), {**base, "candidates": list(reversed(items))}, self.config)
        self.assertEqual(first, second)

    def test_cli_writes_auditable_schedule(self):
        state = empty_state()
        request = {
            "schema_version": "1.0",
            "available_minutes": 30,
            "as_of": "2026-08-10T00:00:00Z",
            "phase_subjects": ["english"],
            "candidates": [candidate("english-reading", "english")],
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state_path = root / "state.json"
            request_path = root / "request.json"
            output_path = root / "schedule.json"
            state_path.write_text(json.dumps(state), encoding="utf-8")
            request_path.write_text(json.dumps(request), encoding="utf-8")
            code = schedule_main([
                "--state", str(state_path),
                "--request", str(request_path),
                "--config", str(DEFAULT_CONFIG),
                "--output", str(output_path),
            ])
            self.assertEqual(code, 0)
            payload = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["scheduled_minutes"], 30)
            self.assertIn("score_breakdown", payload["selected_tasks"][0])

    def test_subject_activation_blocks_candidates_before_activation(self):
        config = {**self.config, "subject_activation": {"math_contest": "2026-10-01T00:00:00+08:00"}}
        request = {
            "schema_version": "1.0",
            "available_minutes": 60,
            "as_of": "2026-09-30T23:59:00+08:00",
            "phase_subjects": ["math_contest"],
            "candidates": [candidate("contest-baseline", "math_contest", 60)],
        }
        result = build_schedule(empty_state(), request, config)
        self.assertEqual(result["selected_tasks"], [])
        self.assertEqual(result["excluded_candidates"], [{"task_id": "contest-baseline", "reason": "subject_not_active"}])


if __name__ == "__main__":
    unittest.main()
