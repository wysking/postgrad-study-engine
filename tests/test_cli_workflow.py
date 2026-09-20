from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.append_event import main as append_main
from scripts.build_context_capsule import main as capsule_main
from scripts.rebuild_state import main as rebuild_main
from scripts.schedule_global import DEFAULT_CONFIG, main as schedule_main
from scripts.validate_events import main as validate_main


ROOT = Path(__file__).resolve().parents[1]


class CliWorkflowTests(unittest.TestCase):
    def test_isolated_event_to_schedule_workflow(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            ledger = work / "learning_events.jsonl"
            state = work / "derived_state.json"
            capsule = work / "context_capsule.md"
            schedule = work / "schedule.json"

            self.assertEqual(append_main([
                "--event", str(ROOT / "examples" / "attempt_clean_correct.json"),
                "--events", str(ledger),
            ]), 0)
            self.assertEqual(validate_main(["--events", str(ledger)]), 0)
            self.assertEqual(rebuild_main([
                "--events", str(ledger),
                "--units", str(ROOT / "state" / "knowledge_units.json"),
                "--output", str(state),
            ]), 0)
            self.assertEqual(capsule_main([
                "--state", str(state),
                "--output", str(capsule),
                "--as-of", "2026-08-14T09:00:00+08:00",
            ]), 0)
            self.assertEqual(schedule_main([
                "--state", str(state),
                "--request", str(ROOT / "examples" / "schedule_request.json"),
                "--config", str(DEFAULT_CONFIG),
                "--output", str(schedule),
            ]), 0)

            rebuilt = json.loads(state.read_text(encoding="utf-8"))
            planned = json.loads(schedule.read_text(encoding="utf-8"))
            self.assertEqual(rebuilt["event_count"], 1)
            self.assertEqual(rebuilt["units"]["math.calculus.limit.equivalent_substitution"]["clean_independent_correct"], 1)
            self.assertIn("math.calculus.limit.equivalent_substitution", capsule.read_text(encoding="utf-8"))
            self.assertGreaterEqual(len(planned["selected_tasks"]), 1)
            self.assertLessEqual(planned["scheduled_minutes"], planned["available_minutes"])


if __name__ == "__main__":
    unittest.main()
