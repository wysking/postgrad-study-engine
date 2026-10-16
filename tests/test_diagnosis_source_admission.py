"""Fictional new-write provenance guards; historical 1.0 records stay readable."""

import json

from scripts.contracts import load_jsonl
from scripts.process_inbox import process_file
from tests.fictional_release_vault import FictionalMobileVault, START, UNIT


class DiagnosisSourceAdmissionTests(FictionalMobileVault):
    def setUp(self):
        super().setUp()
        self.register(["independent"])

    def unclear(self):
        event = self.attempt(result="partial", process_check="not_available")
        event.update(event_id="fictional-unclear", timestamp=START,
                     transcription_uncertainty=["Fictional critical sign cannot be read."])
        return event

    def diagnosis(self, **fields):
        return {"schema_version": "1.0", "event_id": "fictional-confirmation",
                "timestamp": "2026-08-10T09:20:00Z", "event_type": "diagnosis",
                "subject": "math", "unit_ids": [UNIT], "diagnosis": {
                    "diagnosis_id": "fictional-source-episode", "question_id": "fictional-followup",
                    "status": "confirmed", "generated_by": "joint",
                    "first_divergence": "Fictional sign at the critical step.",
                    "learner_verdict": "Fictional declared verification; text alone is not proof.",
                    "confirmation_method": "draft_check", "evidence_refs": ["fictional-unclear"], **fields}}

    def submit(self, operation, payload):
        self.sequence += 1
        request = {"schema_version": "1.0", "request_id": f"fictional-source-{self.sequence}",
                   "created_at": START, "operation": operation, "payload": payload}
        path = self.root / "inbox" / (request["request_id"] + ".json")
        path.write_text(json.dumps(request), encoding="utf-8")
        return process_file(self.root, path)

    def assert_rejected(self, diagnosis):
        path = self.root / "events/learning_events.jsonl"
        before = path.read_bytes() if path.exists() else None
        response = self.submit("record_diagnosis", {"event": diagnosis})
        self.assertEqual(response["status"], "failed")
        self.assertIn("ambiguous draft", response["error"]["message"])
        self.assertEqual(path.read_bytes() if path.exists() else None, before)
        self.assertNotIn("fictional-source-episode", self.state()["diagnoses"])

    def test_unclear_hypothesis_remains_available_without_confirmed_error(self):
        self.call("record_attempt", {"event": self.unclear()})
        for status in ("hypothesized", "unresolved"):
            diagnosis = self.diagnosis(status=status, confirmation_method="not_confirmed",
                                       diagnosis_id="fictional-" + status)
            diagnosis["event_id"] = "fictional-" + status
            self.call("record_diagnosis", {"event": diagnosis})
        self.assertEqual(self.state()["error_patterns"], {})

    def test_own_uncertainty_cannot_be_confirmed_by_declared_draft_check(self):
        diagnosis = self.diagnosis()
        diagnosis["diagnosis"].pop("evidence_refs")
        diagnosis["transcription_uncertainty"] = ["Fictional illegible step."]
        self.assert_rejected(diagnosis)

    def test_referenced_uncertainty_is_guarded_even_if_omitted_from_diagnosis(self):
        self.call("record_attempt", {"event": self.unclear()})
        self.assert_rejected(self.diagnosis())

    def test_clear_but_unrelated_question_does_not_confirm_ambiguous_source(self):
        self.call("record_attempt", {"event": self.unclear()})
        clear = self.attempt(question_id="fictional-unrelated-question")
        self.call("record_attempt", {"event": clear})
        self.assert_rejected(self.diagnosis(evidence_refs=["fictional-unclear", clear["event_id"]]))

    def test_future_corroboration_is_not_available_to_an_earlier_diagnosis(self):
        self.call("record_attempt", {"event": self.unclear()})
        clear = self.attempt()
        clear["timestamp"] = "2026-08-11T09:00:00Z"
        self.call("record_attempt", {"event": clear})
        self.assert_rejected(self.diagnosis(evidence_refs=["fictional-unclear", clear["event_id"]]))

    def test_clear_related_attempt_can_corroborate_without_rewriting_unclear_source(self):
        unclear = self.unclear()
        self.call("record_attempt", {"event": unclear})
        clear = self.attempt(result="incorrect", process_check="suspicious",
                             evidence="Fictional clear original sign step, independently checked.")
        self.call("record_attempt", {"event": clear})
        self.call("record_diagnosis", {"event": self.diagnosis(evidence_refs=[unclear["event_id"], clear["event_id"]])})
        self.assertEqual(self.state()["diagnoses"]["fictional-source-episode"]["status"], "confirmed")
        self.assertEqual(load_jsonl(self.root / "events/learning_events.jsonl")[0], unclear)

    def test_explicit_episode_link_can_supply_a_different_question(self):
        self.call("record_attempt", {"event": self.unclear()})
        clear = self.attempt(question_id="fictional-new-variant", parent_diagnosis_id="fictional-source-episode")
        self.call("record_attempt", {"event": clear})
        self.call("record_diagnosis", {"event": self.diagnosis(evidence_refs=["fictional-unclear", clear["event_id"]])})
        self.assertEqual(self.state()["diagnoses"]["fictional-source-episode"]["status"], "confirmed")

    def test_corroboration_must_cover_every_affected_unit(self):
        other = "math.fictional.other_source_unit"
        self.register(["independent"], unit_id=other)
        self.call("record_attempt", {"event": self.unclear()})
        clear = self.attempt()
        self.call("record_attempt", {"event": clear})
        diagnosis = self.diagnosis(evidence_refs=["fictional-unclear", clear["event_id"]])
        diagnosis["unit_ids"].append(other)
        self.assert_rejected(diagnosis)

    def test_invalid_confirmation_rolls_back_an_entire_new_batch(self):
        result = self.submit("save_session_result", {"events": [self.unclear(), self.diagnosis()]})
        self.assertEqual(result["status"], "failed")
        self.assertFalse((self.root / "events/learning_events.jsonl").exists())

    def test_clear_corroboration_in_the_same_batch_is_usable(self):
        clear = self.attempt()
        diagnosis = self.diagnosis(evidence_refs=["fictional-unclear", clear["event_id"]])
        self.call("save_session_result", {"events": [self.unclear(), clear, diagnosis]})
        self.assertEqual(len(load_jsonl(self.root / "events/learning_events.jsonl")), 3)

    def test_legacy_unclear_confirmation_stays_readable_and_idempotent(self):
        unclear, diagnosis = self.unclear(), self.diagnosis()
        path = self.root / "events/learning_events.jsonl"
        path.parent.mkdir(exist_ok=True)
        prefix = (json.dumps(unclear) + "\n" + json.dumps(diagnosis) + "\n").encode()
        path.write_bytes(prefix)
        self.assertEqual(len(load_jsonl(path)), 2)
        # Existing identical records are not reclassified by a new-write gate.
        self.call("record_diagnosis", {"event": diagnosis})
        self.assertEqual(path.read_bytes(), prefix)
        self.call("record_attempt", {"event": self.attempt()})
        self.assertTrue(path.read_bytes().startswith(prefix))
