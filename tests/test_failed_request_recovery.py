"""Fictional same-request recovery tests; no production receipts are used."""
from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch

from scripts import process_inbox
from scripts.contracts import ContractError
from tests import test_mobile_requests as fixtures
from tests.test_mobile_requests import event, request


class FailedRequestRecoveryTests(unittest.TestCase):
    # Reuse only temporary-Vault setup, not the parent's test methods.
    make_vault = fixtures.MobileRequestTests.make_vault
    write_request = fixtures.MobileRequestTests.write_request

    def failed_request(self):
        root = self.make_vault()
        req = request("fictional-recovery", "record_attempt",
                      {"event": event("fictional-recovery-attempt")})
        path = self.write_request(root, req)
        with patch("scripts.process_inbox._refresh_exports", side_effect=OSError("Fictional export failure")):
            failed = process_inbox.process_file(root, path)
        self.assertEqual(failed["status"], "failed")
        return root, req, path, failed

    def test_failed_receipt_remains_stable_without_explicit_recovery(self):
        root, req, path, failed = self.failed_request()
        self.assertEqual(process_inbox.process_file(root, path), failed)
        self.assertFalse((root / "events/learning_events.jsonl").exists())

    def test_reviewed_same_request_recovers_and_preserves_prior_failure(self):
        root, req, path, failed = self.failed_request()
        recovered = process_inbox.process_file(root, path, retry_failed=True)
        self.assertEqual(recovered["status"], "succeeded")
        self.assertEqual(recovered["request_hash"], failed["request_hash"])
        self.assertEqual(recovered["result"]["recovery"]["prior_failed_receipt"], failed)
        self.assertEqual(len((root / "events/learning_events.jsonl").read_text().splitlines()), 1)
        self.assertTrue((root / "exports/latest.json").exists())
        self.assertEqual(json.loads((root / "outbox" / f"{req['request_id']}.json").read_text()), recovered)
        self.assertEqual(process_inbox.process_file(root, path), recovered)
        self.assertEqual(process_inbox.process_file(root, path, retry_failed=True), recovered)

    def test_legacy_partial_append_is_reconciled_without_a_second_event(self):
        root, req, path, failed = self.failed_request()
        ledger = root / "events/learning_events.jsonl"
        # Fictional old-version failure: event persisted, exports/receipt failed.
        ledger.write_text(json.dumps(req["payload"]["event"]) + "\n", encoding="utf-8")
        before = ledger.read_bytes()
        recovered = process_inbox.process_file(root, path, retry_failed=True)
        self.assertEqual(recovered["status"], "succeeded")
        self.assertEqual(recovered["result"]["archived_event_ids"], [])
        self.assertEqual(recovered["result"]["already_present"], ["fictional-recovery-attempt"])
        self.assertEqual(ledger.read_bytes(), before)
        self.assertTrue((root / "exports/latest.json").exists())

    def test_changed_payload_cannot_reuse_failed_request_identity(self):
        root, req, path, failed = self.failed_request()
        receipt = root / "outbox" / f"{req['request_id']}.json"
        before = receipt.read_bytes()
        req["payload"]["event"]["attempt"]["result"] = "incorrect"
        self.write_request(root, req)
        with self.assertRaisesRegex(ContractError, "different receipt"):
            process_inbox.process_file(root, path, retry_failed=True)
        self.assertEqual(receipt.read_bytes(), before)
        self.assertFalse((root / "events/learning_events.jsonl").exists())

    def test_conflicting_legacy_event_cannot_be_overwritten_by_recovery(self):
        root, req, path, failed = self.failed_request()
        item = req["payload"]["event"].copy()
        item["attempt"] = {**item["attempt"], "result": "incorrect"}
        ledger = root / "events/learning_events.jsonl"
        ledger.write_text(json.dumps(item) + "\n", encoding="utf-8")
        before = ledger.read_bytes()
        receipt = root / "outbox" / f"{req['request_id']}.json"
        receipt_before = receipt.read_bytes()
        with self.assertRaises(ContractError):
            process_inbox.process_file(root, path, retry_failed=True)
        self.assertEqual(ledger.read_bytes(), before)
        self.assertEqual(receipt.read_bytes(), receipt_before)

    def test_recovery_failure_preserves_failed_receipt_and_prior_outputs(self):
        root, req, path, failed = self.failed_request()
        receipt = root / "outbox" / f"{req['request_id']}.json"
        before = receipt.read_bytes()
        with patch("scripts.process_inbox._refresh_exports", side_effect=OSError("Fictional retry failure")):
            with self.assertRaisesRegex(OSError, "retry failure"):
                process_inbox.process_file(root, path, retry_failed=True)
        self.assertEqual(receipt.read_bytes(), before)
        self.assertFalse((root / "events/learning_events.jsonl").exists())

    def test_recovered_receipt_publication_failure_rolls_back_to_old_failed_receipt(self):
        root, req, path, failed = self.failed_request()
        receipt = root / "outbox" / f"{req['request_id']}.json"
        before = receipt.read_bytes()
        writer = process_inbox._write_bytes_atomic

        def fail_receipt(destination, content):
            if destination == receipt:
                raise OSError("Fictional recovered receipt failure")
            writer(destination, content)

        with patch("scripts.process_inbox._write_bytes_atomic", side_effect=fail_receipt):
            with self.assertRaisesRegex(OSError, "recovered receipt failure"):
                process_inbox.process_file(root, path, retry_failed=True)
        self.assertEqual(receipt.read_bytes(), before)
        self.assertFalse((root / "events/learning_events.jsonl").exists())
        self.assertFalse((root / "exports/latest.json").exists())

    def test_recovery_requires_a_failed_receipt_and_single_requested_file(self):
        root = self.make_vault()
        req = request("fictional-no-failure", "record_attempt",
                      {"event": event("fictional-no-failure-attempt")})
        path = self.write_request(root, req)
        with self.assertRaisesRegex(ContractError, "existing same-ID failed"):
            process_inbox.process_file(root, path, retry_failed=True)
        with redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as stopped:
                process_inbox.main(["--vault-root", str(root), "--retry-failed"])
        self.assertEqual(stopped.exception.code, 2)

    def test_cli_recovery_uses_original_request_and_reports_success(self):
        root, req, path, failed = self.failed_request()
        output = io.StringIO()
        with redirect_stdout(output):
            code = process_inbox.main(["--vault-root", str(root), "--request", str(path), "--retry-failed"])
        self.assertEqual(code, 0)
        response = json.loads(output.getvalue())["responses"][0]
        self.assertEqual(response["status"], "succeeded")
        self.assertEqual(response["request_id"], req["request_id"])
        self.assertEqual(response["result"]["recovery"]["prior_failed_receipt"], failed)


if __name__ == "__main__":
    unittest.main()
