"""Fictional direct-API and byte-prefix preservation regressions."""

import json
import tempfile
import unittest
from pathlib import Path

from scripts.contracts import ContractError, append_event_atomic, load_jsonl, validate_knowledge_unit
from scripts.reducer import rebuild_state
from tests.test_error_loop import attempt_event, diagnosis_event


class ContractHardeningTests(unittest.TestCase):
    def test_direct_reducer_rejects_duplicate_event_identity(self):
        event = attempt_event("fictional-duplicate", "2026-08-10T09:00:00Z")
        with self.assertRaisesRegex(ContractError, "duplicate event_id"):
            rebuild_state([event, event])

    def test_direct_reducer_requires_a_legal_latest_revision_chain(self):
        first = diagnosis_event("fictional-first", "2026-08-10T09:00:00Z", "hypothesized")
        second = diagnosis_event("fictional-second", "2026-08-10T09:10:00Z", "confirmed")
        with self.assertRaisesRegex(ContractError, "requires supersedes_event_id"):
            rebuild_state([first, second])

    def test_append_retains_bom_crlf_whitespace_and_no_final_newline_prefixes(self):
        first = attempt_event("fictional-prefix", "2026-08-10T09:00:00Z")
        second = attempt_event("fictional-appended", "2026-08-10T09:10:00Z")
        line = json.dumps(first).encode()
        for prefix in (b"\xef\xbb\xbf  " + line + b"\r\n\r\n", line, b" " + line + b" \n  "):
            with self.subTest(prefix_style=prefix[:4]), tempfile.TemporaryDirectory() as temporary:
                path = Path(temporary) / "fictional.jsonl"
                path.write_bytes(prefix)
                append_event_atomic(path, second)
                self.assertTrue(path.read_bytes().startswith(prefix))
                self.assertEqual(load_jsonl(path), [first, second])

    def test_boolean_duration_is_rejected_and_real_integer_is_valid(self):
        unit = {"schema_version": "1.0", "unit_id": "math.fictional.duration",
                "subject": "math", "title": "Fictional duration"}
        for value in (True, False):
            with self.subTest(value=value), self.assertRaises(ContractError):
                validate_knowledge_unit({**unit, "estimated_minutes": value})
        self.assertEqual(validate_knowledge_unit({**unit, "estimated_minutes": 10})["estimated_minutes"], 10)
