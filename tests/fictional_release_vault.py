"""Temporary fictional mobile fixtures. Never import these into a learner Vault."""

import json
import tempfile
import unittest
from pathlib import Path

from scripts.contracts import load_json
from scripts.process_inbox import process_file
from scripts.schedule_global import DEFAULT_CONFIG


START = "2026-08-10T09:00:00Z"
LATER = "2026-08-10T09:10:00Z"
NEXT_DAY = "2026-08-11T09:00:00Z"
ACTIVATION = "2026-08-12T00:00:00Z"
UNIT = "math.fictional.release_check"


class FictionalMobileVault(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        (self.root / "config/personal").mkdir(parents=True)
        (self.root / "inbox").mkdir()
        config = load_json(DEFAULT_CONFIG)
        config["phase_subjects"] = ["math", "english", "math_contest"]
        config["subject_activation"] = {"math_contest": ACTIVATION}
        (self.root / "config/personal/scheduler.json").write_text(
            json.dumps(config), encoding="utf-8"
        )
        self.sequence = 0

    def call(self, operation, payload):
        self.sequence += 1
        request = {
            "schema_version": "1.0", "request_id": f"fictional-release-{self.sequence}",
            "created_at": START, "operation": operation, "payload": payload,
        }
        path = self.root / "inbox" / f"{request['request_id']}.json"
        path.write_text(json.dumps(request), encoding="utf-8")
        response = process_file(self.root, path)
        self.assertEqual(response["status"], "succeeded", response)
        return response

    def register(self, targets, subject="math", unit_id=UNIT):
        self.call("register_unit", {"unit": {
            "schema_version": "1.0", "unit_id": unit_id, "subject": subject,
            "title": "Fictional release regression", "estimated_minutes": 10,
            "evidence_targets": targets,
        }})

    def state(self):
        return load_json(self.root / "state/derived_state.json")

    def schedule(self, **fields):
        request = {"schema_version": "1.0", "available_minutes": 20,
                   "as_of": START, "phase_subjects": ["math"],
                   "max_subject_share": 1, **fields}
        return self.call("request_schedule", {"request": request})["result"]["schedule"]

    def attempt(self, *, activity="solve", mode="independent", assistance=0, **fields):
        attempt = {"question_id": "fictional-followup", "result": "correct",
                   "answer_mode": mode, "assistance_level": assistance,
                   "process_check": "clean", "evidence": "Fictional observed response.",
                   **fields}
        return {"schema_version": "1.0", "event_id": "fictional-answer",
                "timestamp": LATER, "event_type": "attempt", "subject": "math",
                "unit_ids": [UNIT], "activity": activity, "attempt": attempt}


def external(task_id="fictional-external", subject="math", **fields):
    return {"task_id": task_id, "unit_id": UNIT, "subject": subject,
            "task_type": "practice", "activity": "solve", "estimated_minutes": 10,
            "expected_score_gain": 1, "fatigue_cost": 0, **fields}
