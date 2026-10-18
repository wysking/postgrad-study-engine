"""Fictional, isolated observations; never publish these to a learner Vault."""

from __future__ import annotations

import hashlib
import io
import json
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from scripts import process_inbox, study_records
from scripts.contracts import ContractError, load_json, validate_study_record_payload
from tests.fictional_release_vault import FictionalMobileVault, START, NEXT_DAY


class StudyRecordTests(FictionalMobileVault):
    def write_request(self, name="fictional-note", payload=None):
        request = {
            "schema_version": "1.0", "request_id": name, "created_at": START,
            "operation": "save_study_record", "client": "fictional-client",
            "payload": payload if payload is not None else {"summary": "Fictional incomplete observation."},
        }
        path = self.root / "inbox" / f"{name}.json"
        path.write_text(json.dumps(request), encoding="utf-8")
        return path

    def record_rows(self):
        return study_records.read_records(self.root / study_records.RECORDS_RELATIVE)[1]

    def protected_bytes(self):
        paths = ["events/learning_events.jsonl", "state/knowledge_units.json",
                 "state/derived_state.json", "exports/latest.json", "exports/latest.md",
                 "config/personal/scheduler.json"]
        return {p: (self.root / p).read_bytes() if (self.root / p).exists() else None for p in paths}

    def test_minimal_record_does_not_assess_or_change_learning_state(self):
        self.register(["independent"])
        before = self.protected_bytes()
        response = process_inbox.process_file(self.root, self.write_request())
        self.assertEqual(response["status"], "succeeded")
        self.assertEqual(response["result"]["record_id"], "fictional-note")
        self.assertEqual(response["result"]["evaluation_status"], "not_requested")
        self.assertEqual(before, self.protected_bytes())
        row = self.record_rows()[0]
        self.assertEqual(row["summary"], "Fictional incomplete observation.")
        for field in ("occurred_at", "occurred_on", "assistance_level", "confidence", "result", "attempt"):
            self.assertNotIn(field, row)
        self.assertEqual(row["request_hash"], response["request_hash"])

    def test_record_is_independent_of_corrupt_assessment_inputs(self):
        for relative in ("events/learning_events.jsonl", "state/knowledge_units.json",
                         "config/personal/scheduler.json", "exports/latest.json"):
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"fictional invalid assessment input")
        before = self.protected_bytes()
        response = process_inbox.process_file(self.root, self.write_request())
        self.assertEqual(response["status"], "succeeded", response)
        self.assertEqual(before, self.protected_bytes())

    def test_record_needs_no_scheduler_or_registered_subject(self):
        (self.root / "config/personal/scheduler.json").unlink()
        response = process_inbox.process_file(self.root, self.write_request(payload={
            "summary": "Fictional observation, not a baseline or assessment.",
            "subject_label": "Unregistered fictional subject",
        }))
        self.assertEqual(response["status"], "succeeded")
        self.assertFalse((self.root / "state/knowledge_units.json").exists())
        self.assertFalse((self.root / "events/learning_events.jsonl").exists())

    def test_date_only_and_exact_time_preserve_observed_precision(self):
        for number, fields in enumerate(({"occurred_on": "2026-08-09"},
                                          {"occurred_at": "2026-08-09T11:00:00+08:00"})):
            response = process_inbox.process_file(self.root, self.write_request(
                f"fictional-time-{number}", {"summary": "Fictional dated observation.", **fields}))
            self.assertEqual(response["status"], "succeeded")
            row = self.record_rows()[-1]
            self.assertEqual({k: row[k] for k in fields}, fields)
            other = "occurred_at" if "occurred_on" in fields else "occurred_on"
            self.assertNotIn(other, row)

    def test_invalid_payloads_fail_without_recording(self):
        invalid = [{}, {"summary": " "}, {"summary": None}, {"summary": {}},
                   {"summary": "x" * 12001},
                   {"summary": "Fictional", "assistance_level": 0},
                   {"summary": "Fictional", "subject_label": False},
                   {"summary": "Fictional", "occurred_at": "2026-08-09T11:00:00"},
                   {"summary": "Fictional", "occurred_on": "2026-02-30"},
                   {"summary": "Fictional", "occurred_on": "20260809"},
                   {"summary": "Fictional", "occurred_on": "2026-08-09", "occurred_at": START},
                   {"summary": "Fictional", "messages": []}]
        for number, payload in enumerate(invalid):
            with self.subTest(payload=payload):
                response = process_inbox.process_file(self.root, self.write_request(f"fictional-bad-{number}", payload))
                self.assertEqual(response["status"], "failed")
                self.assertFalse((self.root / study_records.RECORDS_RELATIVE).exists())
        with self.assertRaises(ContractError):
            validate_study_record_payload([])

    def test_request_replay_keeps_record_time_and_all_published_bytes(self):
        path = self.write_request()
        first = process_inbox.process_file(self.root, path)
        before = {p: p.read_bytes() for p in self.root.rglob("*") if p.is_file() and p.name != ".study-inbox.lock"}
        request = load_json(path)
        path.write_text(json.dumps(request, indent=4), encoding="utf-8")
        second = process_inbox.process_file(self.root, path)
        self.assertEqual(first, second)
        for p, original in before.items():
            if p != path:
                self.assertEqual(p.read_bytes(), original)
        self.assertEqual(len(self.record_rows()), 1)

    def test_changed_same_id_preserves_original_record_and_receipt(self):
        path = self.write_request()
        first = process_inbox.process_file(self.root, path)
        original = (self.root / study_records.RECORDS_RELATIVE).read_bytes()
        self.write_request(payload={"summary": "Changed fictional observation."})
        with self.assertRaises(ContractError):
            process_inbox.process_file(self.root, path)
        self.assertEqual((self.root / study_records.RECORDS_RELATIVE).read_bytes(), original)
        self.assertEqual(load_json(self.root / "outbox/fictional-note.json"), first)

    def test_missing_receipt_recovery_keeps_first_received_time(self):
        path = self.write_request()
        with patch("scripts.process_inbox._utc_now", return_value=START):
            first = process_inbox.process_file(self.root, path)
        original = (self.root / study_records.RECORDS_RELATIVE).read_bytes()
        (self.root / "outbox/fictional-note.json").unlink()
        with patch("scripts.process_inbox._utc_now", return_value=NEXT_DAY):
            recovered = process_inbox.process_file(self.root, path)
        self.assertEqual(recovered["status"], "succeeded")
        self.assertEqual(recovered["result"]["received_at"], first["result"]["received_at"])
        self.assertEqual(recovered["result"]["persistence_action"], "already_present")
        self.assertEqual((self.root / study_records.RECORDS_RELATIVE).read_bytes(), original)

    def test_append_preserves_bom_whitespace_and_missing_newline(self):
        process_inbox.process_file(self.root, self.write_request("fictional-prefix"))
        row = self.record_rows()[0]
        prefix = b"\xef\xbb\xbf\r\n" + json.dumps(row, ensure_ascii=False).encode("utf-8") + b"  "
        path = self.root / study_records.RECORDS_RELATIVE
        path.write_bytes(prefix)
        response = process_inbox.process_file(self.root, self.write_request("fictional-after-prefix"))
        self.assertEqual(response["status"], "succeeded")
        self.assertTrue(path.read_bytes().startswith(prefix + b"\n"))
        self.assertEqual(len(self.record_rows()), 2)

    def test_corrupt_or_duplicate_source_records_cannot_degrade_to_success(self):
        process_inbox.process_file(self.root, self.write_request("fictional-seed"))
        path = self.root / study_records.RECORDS_RELATIVE
        valid = path.read_bytes()
        for number, broken in enumerate((b"{bad\n", valid + valid)):
            path.write_bytes(broken)
            response = process_inbox.process_file(self.root, self.write_request(f"fictional-corrupt-{number}"))
            self.assertEqual(response["status"], "failed")
            self.assertEqual(path.read_bytes(), broken)

    def test_conflicting_or_malformed_orphan_record_is_not_overwritten(self):
        path = self.write_request()
        process_inbox.process_file(self.root, path)
        ledger = self.root / study_records.RECORDS_RELATIVE
        row = self.record_rows()[0]
        row["summary"] = "Conflicting fictional stored content."
        raw = json.dumps(row).encode() + b"\n"
        ledger.write_bytes(raw)
        (self.root / "outbox/fictional-note.json").unlink()
        response = process_inbox.process_file(self.root, path)
        self.assertEqual(response["status"], "failed")
        self.assertEqual(ledger.read_bytes(), raw)

    def test_known_index_error_saves_record_with_fresh_unavailable_marker(self):
        process_inbox.process_file(self.root, self.write_request("fictional-index-seed"))
        with patch("scripts.study_records.build_index", side_effect=study_records.StudyRecordIndexError("Fictional projection issue")):
            response = process_inbox.process_file(self.root, self.write_request("fictional-index-degraded"))
        self.assertEqual(response["status"], "succeeded")
        self.assertEqual(response["result"]["record_index_status"], "unavailable")
        self.assertTrue(response["result"]["warnings"])
        index = load_json(self.root / study_records.INDEX_RELATIVE)
        self.assertEqual(index["status"], "unavailable")
        self.assertEqual(index["stored_count"], 2)
        self.assertNotIn("recent_records", index)
        raw = (self.root / study_records.RECORDS_RELATIVE).read_bytes()
        self.assertEqual(index["records_revision"], hashlib.sha256(raw).hexdigest())

    def test_index_storage_failure_rolls_back_the_new_record(self):
        process_inbox.process_file(self.root, self.write_request("fictional-index-storage-seed"))
        original = (self.root / study_records.RECORDS_RELATIVE).read_bytes()
        with patch("scripts.study_records.dump_json_atomic", side_effect=OSError("Fictional storage issue")):
            response = process_inbox.process_file(self.root, self.write_request("fictional-index-storage-fail"))
        self.assertEqual(response["status"], "failed")
        self.assertEqual((self.root / study_records.RECORDS_RELATIVE).read_bytes(), original)

    def test_record_storage_failure_cannot_publish_success(self):
        with patch("scripts.study_records._write_bytes", side_effect=OSError("Fictional record disk failure")):
            response = process_inbox.process_file(self.root, self.write_request())
        self.assertEqual(response["status"], "failed")
        self.assertFalse((self.root / study_records.RECORDS_RELATIVE).exists())

    def test_unexpected_index_bug_is_not_swallowed(self):
        with patch("scripts.study_records.build_index", side_effect=RuntimeError("Fictional implementation bug")):
            with self.assertRaises(RuntimeError):
                process_inbox.process_file(self.root, self.write_request())
        self.assertFalse((self.root / study_records.RECORDS_RELATIVE).exists())
        self.assertFalse((self.root / "outbox/fictional-note.json").exists())

    def test_receipt_publication_failure_restores_record_and_index(self):
        process_inbox.process_file(self.root, self.write_request("fictional-publication-seed"))
        before = {relative: (self.root / relative).read_bytes() for relative in process_inbox.DURABLE_OUTPUTS if (self.root / relative).exists()}
        path = self.write_request("fictional-publication-fail")
        write = process_inbox._write_bytes_atomic
        def fail_receipt(destination, content):
            if destination == self.root / "outbox/fictional-publication-fail.json":
                raise OSError("Fictional receipt publication failure")
            write(destination, content)
        with patch("scripts.process_inbox._write_bytes_atomic", side_effect=fail_receipt):
            response = process_inbox.process_file(self.root, path)
        self.assertEqual(response["status"], "failed")
        for relative, raw in before.items():
            self.assertEqual((self.root / relative).read_bytes(), raw)

    def test_recent_index_limits_only_view_not_source_records(self):
        for number in range(21):
            response = process_inbox.process_file(self.root, self.write_request(
                f"fictional-recent-{number}", {"summary": "Fictional observation " + "x" * 400}))
            self.assertEqual(response["status"], "succeeded")
        index = load_json(self.root / study_records.INDEX_RELATIVE)
        self.assertEqual(index["stored_count"], 21)
        self.assertEqual(index["unassessed_count"], 21)
        self.assertEqual(len(index["recent_records"]), 20)
        self.assertEqual(index["recent_records"][0]["record_id"], "fictional-recent-20")
        self.assertTrue(index["recent_records"][0]["summary_truncated"])
        self.assertGreater(len(self.record_rows()[0]["summary"]), 300)

    def test_legacy_failure_and_new_success_remain_distinct(self):
        bad = self.write_request("fictional-000-bad", {"summary": ""})
        process_inbox.process_file(self.root, bad)
        self.write_request("fictional-001-good")
        output = io.StringIO()
        with redirect_stdout(output):
            code = process_inbox.main(["--vault-root", str(self.root)])
        self.assertEqual(code, 2)
        self.assertEqual([r["status"] for r in json.loads(output.getvalue())["responses"]], ["failed", "succeeded"])
        self.assertEqual(len(self.record_rows()), 1)
