from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.process_inbox import process_file


def event(event_id: str, *, subject: str = "math") -> dict:
    return {
        "schema_version": "1.0",
        "event_id": event_id,
        "timestamp": "2026-09-20T09:00:00+08:00",
        "event_type": "attempt",
        "subject": subject,
        "unit_ids": [f"{subject}.sample.unit"],
        "activity": "solve",
        "source_ref": "demo-mobile",
        "attempt": {
            "question_id": "demo-question-001",
            "result": "correct",
            "answer_mode": "independent",
            "process_check": "clean",
            "assistance_level": 0,
            "time_minutes": 8,
            "confidence_before": 0.7,
            "evidence": "Fictional test evidence.",
        },
    }


def request(request_id: str, operation: str, payload: dict) -> dict:
    return {
        "schema_version": "1.0",
        "request_id": request_id,
        "created_at": "2026-09-20T09:05:00+08:00",
        "operation": operation,
        "payload": payload,
        "client": "fictional-test-client",
    }


class MobileRequestTests(unittest.TestCase):
    def make_vault(self) -> Path:
        root = Path(tempfile.mkdtemp())
        (root / "config" / "personal").mkdir(parents=True)
        (root / "events").mkdir()
        (root / "state").mkdir()
        (root / "inbox").mkdir()
        (root / "outbox").mkdir()
        (root / "sources").mkdir()
        (root / "state" / "knowledge_units.json").write_text(
            json.dumps({"schema_version": "1.0", "units": []}), encoding="utf-8"
        )
        (root / "config" / "personal" / "scheduler.json").write_text(
            json.dumps({
                "model_version": "test",
                "current_phase": "test",
                "phase_subjects": ["math", "math_contest"],
                "subject_weights": {"math": 1.0, "math_contest": 1.0},
                "subject_activation": {"math_contest": "2026-10-01T00:00:00+08:00"},
                "weights": {
                    "expected_score_gain": 4.0,
                    "forgetting_risk": 2.5,
                    "information_gain": 2.0,
                    "transfer_value": 1.25,
                    "urgency": 2.0,
                    "error_recurrence": 1.5,
                    "fatigue_cost": 1.0,
                },
                "max_subject_share": 0.65,
                "mastery_target": 0.75,
                "prerequisite_threshold": 0.55,
                "beam_limit": 20000,
            }),
            encoding="utf-8",
        )
        return root

    def write_request(self, root: Path, payload: dict) -> Path:
        path = root / "inbox" / f"{payload['request_id']}.json"
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return path

    def test_attempt_is_archived_exported_and_idempotent(self):
        root = self.make_vault()
        req = request("mobile-demo-001", "record_attempt", {"event": event("demo-event-001")})
        path = self.write_request(root, req)

        first = process_file(root, path)
        second = process_file(root, path)

        self.assertEqual(first["status"], "succeeded")
        self.assertEqual(first, second)
        ledger = (root / "events" / "learning_events.jsonl").read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(ledger), 1)
        self.assertTrue((root / "outbox" / "mobile-demo-001.json").exists())
        self.assertTrue((root / "exports" / "latest.json").exists())
        self.assertTrue((root / "exports" / "latest.md").exists())

    def test_contest_baseline_is_not_archived_before_activation(self):
        root = self.make_vault()
        req = request("mobile-demo-contest", "record_contest_baseline", {"event": event("contest-001", subject="math_contest")})
        path = self.write_request(root, req)

        response = process_file(root, path)

        self.assertEqual(response["status"], "failed")
        self.assertIn("not active", response["error"]["message"])
        self.assertFalse((root / "events" / "learning_events.jsonl").exists())

    def test_register_unit_and_schedule_use_current_vault(self):
        root = self.make_vault()
        unit = {
            "schema_version": "1.0",
            "unit_id": "math.sample.unit",
            "subject": "math",
            "title": "Fictional unit",
            "estimated_minutes": 20,
        }
        register = request("mobile-demo-unit", "register_unit", {"unit": unit})
        register_path = self.write_request(root, register)
        self.assertEqual(process_file(root, register_path)["status"], "succeeded")

        schedule = request("mobile-demo-schedule", "request_schedule", {"request": {
            "schema_version": "1.0",
            "available_minutes": 20,
            "as_of": "2026-09-20T09:00:00+08:00",
            "phase_subjects": ["math"],
        }})
        schedule_path = self.write_request(root, schedule)
        response = process_file(root, schedule_path)

        self.assertEqual(response["status"], "succeeded")
        self.assertEqual(response["result"]["schedule"]["scheduled_minutes"], 20)

    def test_project_change_request_stays_pending(self):
        root = self.make_vault()
        req = request("mobile-demo-change", "project_change_request", {
            "title": "Fictional change",
            "description": "Add a future contract test.",
            "acceptance_criteria": ["The existing tests still pass."],
        })
        path = self.write_request(root, req)

        response = process_file(root, path)

        self.assertEqual(response["status"], "pending")
        self.assertTrue((root / "config" / "personal" / "project_change_requests.jsonl").exists())


if __name__ == "__main__":
    unittest.main()
