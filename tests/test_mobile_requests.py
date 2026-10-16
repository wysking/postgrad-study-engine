from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from scripts import process_inbox
from scripts.process_inbox import main, process_file


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

    def test_failed_state_rebuild_does_not_append_an_event(self):
        root = self.make_vault()
        registry_path = root / "state" / "knowledge_units.json"
        registry_path.write_text(json.dumps({"schema_version": "1.0", "units": [{
            "schema_version": "1.0", "unit_id": "math.sample.unit",
            "subject": "english", "title": "Fictional mismatched registry",
        }]}), encoding="utf-8")
        before = registry_path.read_bytes()
        req = request("mobile-demo-conflict", "record_attempt", {"event": event("conflict-001")})

        response = process_file(root, self.write_request(root, req))

        self.assertEqual(response["status"], "failed")
        self.assertFalse((root / "events" / "learning_events.jsonl").exists())
        self.assertEqual(registry_path.read_bytes(), before)

    def test_failed_export_does_not_leave_archived_evidence(self):
        root = self.make_vault()
        req = request("mobile-demo-export-failure", "record_attempt", {"event": event("export-failure-001")})
        with patch("scripts.process_inbox._refresh_exports", side_effect=OSError("Fictional write failure")):
            response = process_file(root, self.write_request(root, req))
        self.assertEqual(response["status"], "failed")
        self.assertFalse((root / "events" / "learning_events.jsonl").exists())

    def test_failed_unit_registration_does_not_change_registry(self):
        root = self.make_vault()
        existing = event("prior-001", subject="english")
        existing["unit_ids"] = ["math.sample.unit"]
        (root / "events" / "learning_events.jsonl").write_text(json.dumps(existing) + "\n", encoding="utf-8")
        registry_path = root / "state" / "knowledge_units.json"
        before = registry_path.read_bytes()
        unit = {"schema_version": "1.0", "unit_id": "math.sample.unit", "subject": "math", "title": "Fictional unit"}
        req = request("mobile-demo-register-failure", "register_unit", {"unit": unit})

        response = process_file(root, self.write_request(root, req))

        self.assertEqual(response["status"], "failed")
        self.assertEqual(registry_path.read_bytes(), before)

    def test_malformed_inbox_does_not_block_later_valid_requests(self):
        root = self.make_vault()
        (root / "inbox" / "000-malformed.json").write_text("{broken", encoding="utf-8")
        good = request("mobile-demo-after-malformed", "record_attempt", {"event": event("after-malformed-001")})
        self.write_request(root, good)

        output = io.StringIO()
        with redirect_stdout(output):
            exit_code = main(["--vault-root", str(root)])

        self.assertEqual(exit_code, 2)
        self.assertEqual(json.loads((root / "outbox" / f"{good['request_id']}.json").read_text())["status"], "succeeded")
        responses = json.loads(output.getvalue())["responses"]
        self.assertEqual([item["status"] for item in responses], ["failed", "succeeded"])

    def test_receipt_publication_failure_restores_existing_outputs(self):
        root = self.make_vault()
        seed = request("mobile-demo-seed", "record_attempt", {"event": event("seed-001")})
        self.assertEqual(process_file(root, self.write_request(root, seed))["status"], "succeeded")
        before = {relative: (root / relative).read_bytes() for relative in process_inbox.DURABLE_OUTPUTS if (root / relative).exists()}
        req = request("mobile-demo-publish-failure", "record_attempt", {"event": event("publish-failure-001")})
        receipt_path = root / "outbox" / f"{req['request_id']}.json"
        atomic_write = process_inbox._write_bytes_atomic

        def fail_receipt(path, content):
            if path == receipt_path:
                raise OSError("Fictional receipt publication failure")
            atomic_write(path, content)

        with patch("scripts.process_inbox._write_bytes_atomic", side_effect=fail_receipt):
            response = process_file(root, self.write_request(root, req))

        self.assertEqual(response["status"], "failed")
        self.assertEqual(json.loads(receipt_path.read_text())["status"], "failed")
        for relative, original in before.items():
            self.assertEqual((root / relative).read_bytes(), original, str(relative))

    def test_invalid_enum_is_a_file_failure_and_does_not_block_the_inbox(self):
        root = self.make_vault()
        bad = request("000-invalid-operation", "record_attempt", {})
        bad["operation"] = []
        self.write_request(root, bad)
        good = request("mobile-demo-after-invalid-enum", "record_attempt", {"event": event("after-invalid-enum-001")})
        self.write_request(root, good)
        with redirect_stdout(io.StringIO()):
            exit_code = main(["--vault-root", str(root)])
        self.assertEqual(exit_code, 2)
        self.assertTrue((root / "outbox" / f"{good['request_id']}.json").exists())


if __name__ == "__main__":
    unittest.main()
