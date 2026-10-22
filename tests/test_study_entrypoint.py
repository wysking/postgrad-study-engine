"""Fictional end-to-end setup, receipts, isolation, probes and local reports."""

import argparse
import copy
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from scripts.contracts import ContractError, load_json, load_jsonl
from scripts.learning_context import (context_for_vault, render_dashboard, render_today,
                                      select_diagnostics, validate_course)
from scripts.study import (init_vault, install_course, main, record_observation,
                           run_demo, submit, verified_receipt, verify_runtime)
from tests.test_learning_models import AS_OF, COURSE, EVENTS, MEMORY


class StudyEntryPointTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / "fictional-a"

    def init(self, root=None, demo=True, course=True):
        target = root or self.root
        init_vault(target, demo=demo)
        if course:
            install_course(target, copy.deepcopy(COURSE))
        return target

    def test_init_is_empty_version_locked_and_refuses_overwrite(self):
        self.init(course=False)
        verify_runtime(self.root)
        self.assertFalse((self.root / "events").exists())
        before = (self.root / "learner.json").read_bytes()
        with self.assertRaises(ContractError):
            init_vault(self.root)
        self.assertEqual((self.root / "learner.json").read_bytes(), before)

    def test_existing_non_vault_directory_is_not_overwritten(self):
        self.root.mkdir()
        (self.root / "keep").write_text("original")
        with self.assertRaises(ContractError):
            init_vault(self.root)
        self.assertEqual((self.root / "keep").read_text(), "original")

    def test_blank_personal_vault_context_runs_without_examples(self):
        self.init(demo=False, course=False)
        context = context_for_vault(self.root, AS_OF)
        self.assertEqual(context["state"]["event_count"], 0)
        self.assertEqual(context["diagnostics"]["selected"], [])
        self.assertIsNone(context["schedule"])

    def test_fictional_course_cannot_seed_personal_vault(self):
        self.init(demo=False, course=False)
        with self.assertRaises(ContractError):
            install_course(self.root, COURSE)
        self.assertFalse((self.root / "state").exists())

    def test_course_installs_units_without_attempts_and_is_repeatable(self):
        self.init()
        install_course(self.root, COURSE)
        context = context_for_vault(self.root, AS_OF)
        self.assertEqual(len(context["state"]["units"]), 9)
        self.assertEqual(context["state"]["event_count"], 0)
        self.assertTrue(all(u["mastery_overall"] is None for u in context["state"]["units"].values()))

    def test_course_cycle_and_conflict_are_rejected_before_new_requests(self):
        self.init()
        before = set((self.root / "inbox").iterdir())
        c = copy.deepcopy(COURSE)
        c["units"][0]["prerequisites"] = [c["units"][1]["unit_id"]]
        with self.assertRaises(ContractError):
            install_course(self.root, c)
        c = copy.deepcopy(COURSE)
        c["units"][0]["title"] = "different"
        with self.assertRaises(ContractError):
            install_course(self.root, c)
        self.assertEqual(set((self.root / "inbox").iterdir()), before)

    def test_real_receipt_hash_and_replay_keep_one_attempt(self):
        self.init()
        e = copy.deepcopy(EVENTS[0])
        r = submit(self.root, "record_attempt", {"event": e}, "fictional-write")
        self.assertEqual(r["status"], "succeeded")
        with redirect_stdout(io.StringIO()):
            self.assertEqual(main(["retry", "--vault", str(self.root), "--request-id", "fictional-write"]), 0)
        self.assertEqual(len(load_jsonl(self.root / "events/learning_events.jsonl")), 1)
        with self.assertRaises(FileExistsError):
            submit(self.root, "record_attempt", {"event": e}, "fictional-write")

    def test_compact_record_does_not_create_assessment(self):
        self.init()
        submit(self.root, "save_study_record", {"summary": "Fictional observed fragment, result unknown."})
        context = context_for_vault(self.root, AS_OF)
        self.assertEqual(context["state"]["event_count"], 0)
        self.assertTrue((self.root / "records/study_records.jsonl").exists())

    def test_old_compact_receipt_requires_its_exact_stored_record(self):
        self.init()
        submit(self.root, "save_study_record", {"summary": "Fictional observation"}, "fictional-compact")
        request_path = self.root / "inbox/fictional-compact.json"
        request = load_json(request_path)
        record_path = self.root / "records/study_records.jsonl"
        original = record_path.read_bytes()
        # Later appends must not invalidate the earlier record's receipt.
        submit(self.root, "save_study_record", {"summary": "Fictional later observation"})
        verified_receipt(self.root, request_path, request)
        record_path.write_bytes(b"")
        with self.assertRaises(ContractError):
            verified_receipt(self.root, request_path, request)
        stored = json.loads(original)
        stored["summary"] = "Tampered fictional content"
        record_path.write_text(json.dumps(stored) + "\n", encoding="utf-8")
        with self.assertRaises(ContractError):
            verified_receipt(self.root, request_path, request)

    def test_probe_ids_are_namespaced_by_course(self):
        self.init()
        context = context_for_vault(self.root, AS_OF)
        other = copy.deepcopy(COURSE)
        other["course_id"] = "fictional-another-course"
        courses = [COURSE, other]
        registry = {u["unit_id"]: u for u in COURSE["units"]}
        cfg = load_json(self.root / "config/personal/scheduler.json")
        result = select_diagnostics(registry, context["state"], context["models"], courses, cfg, AS_OF)
        candidates = result["candidates"]
        self.assertEqual(len(candidates), 2 * len(context["diagnostics"]["candidates"]))
        self.assertEqual(len({c["probe_id"] for c in candidates}), len(candidates))
        self.assertEqual({c["course_id"] for c in candidates}, {c["course_id"] for c in courses})
        with self.assertRaises(ContractError):
            select_diagnostics(registry, context["state"], context["models"], [COURSE, COURSE], cfg, AS_OF)

    def test_incomplete_formal_fields_stop_before_submission(self):
        self.init()
        args = argparse.Namespace(summary="Fictional fragment", result="correct", mode=None, process=None,
                                  assistance=None, question=None, unit=None, activity=None, occurred_at=None,
                                  delayed_days=None, request_id=None)
        before = set((self.root / "inbox").iterdir())
        with self.assertRaises(ContractError):
            record_observation(self.root, args)
        self.assertEqual(set((self.root / "inbox").iterdir()), before)

    def test_runtime_mismatch_blocks_writes(self):
        self.init(course=False)
        p = self.root / "engine.lock.json"
        lock = load_json(p)
        lock["commit"] = "0" * 40
        p.write_text(json.dumps(lock))
        with self.assertRaises(ContractError):
            submit(self.root, "save_study_record", {"summary": "Fictional fragment"})
        self.assertEqual(list((self.root / "inbox").iterdir()), [])

    def test_dirty_runtime_cannot_create_a_misleading_exact_lock(self):
        with patch("scripts.study.subprocess.check_output", side_effect=["a" * 40, " M scripts/study.py\n"]):
            with self.assertRaises(ContractError):
                init_vault(self.root)
        self.assertFalse(self.root.exists())

    def test_two_learners_do_not_share_events_models_or_reports(self):
        self.init()
        other = self.init(self.base / "fictional-b")
        before = context_for_vault(other, AS_OF)
        submit(self.root, "record_attempt", {"event": EVENTS[0]})
        after = context_for_vault(other, AS_OF)
        self.assertEqual(before, after)
        self.assertNotEqual(context_for_vault(self.root, AS_OF)["models"]["model_id"], after["models"]["model_id"])

    def test_unknown_prerequisite_creates_hypothesis_not_failure(self):
        self.init()
        c = context_for_vault(self.root, AS_OF)
        self.assertTrue(c["diagnostics"]["selected"])
        self.assertTrue(all(x["status"] == "hypothesis_not_confirmed" for x in c["diagnostics"]["selected"]))
        self.assertTrue(all(x["reason"] == "evidence_insufficient_needs_check" for x in c["diagnostics"]["candidates"]))
        self.assertEqual(c["state"]["diagnoses"], {})

    def test_budget_and_activation_filter_probes(self):
        self.init()
        c = context_for_vault(self.root, AS_OF, minutes=1)
        self.assertEqual(c["diagnostics"]["selected"], [])
        p = self.root / "config/personal/scheduler.json"
        cfg = load_json(p)
        cfg["phase_subjects"] = ["english"]
        cfg["subject_activation"] = {"english": "2030-01-01T00:00:00Z"}
        p.write_text(json.dumps(cfg))
        c = context_for_vault(self.root, AS_OF)
        self.assertEqual(c["diagnostics"]["selected"], [])
        self.assertEqual(c["due_work"], [])

    def test_future_confirmation_cannot_become_a_probe_today(self):
        self.init()
        e = copy.deepcopy(EVENTS[0])
        e["timestamp"] = AS_OF.isoformat()
        e["attempt"].update(answer_mode="assisted", assistance_level=1)
        submit(self.root, "record_attempt", {"event": e})
        c = context_for_vault(self.root, AS_OF)
        self.assertTrue(any(x["reason"] == "existing_confirmation_not_due" for x in c["diagnostics"]["excluded"]))

    def test_dashboard_escapes_untrusted_titles_and_unknown_is_visible(self):
        self.init()
        c = context_for_vault(self.root, AS_OF)
        next(iter(c["state"]["units"].values()))["title"] = "<script>alert('fictional')</script>"
        page = render_dashboard(c)
        self.assertNotIn("<script>", page)
        self.assertIn("&lt;script&gt;", page)
        self.assertIn("Unknown / 未知", page)
        self.assertNotIn("https://", page)

    def test_fictional_demo_runs_full_loop_without_real_vault(self):
        c = run_demo(self.root)
        self.assertEqual(c["state"]["event_count"], 15)
        self.assertEqual(c["learner"]["mode"], "demo")
        self.assertEqual(c["models"]["memory"][MEMORY]["status"], "fitted_uncalibrated")
        self.assertTrue((self.root / "reports/demo.html").exists())
        self.assertIn("DEMO", render_today(c))
        self.assertTrue(any(p["unit_id"] == MEMORY and p["reason"] == "observed_failure_needs_check"
                            for p in c["diagnostics"]["selected"]))
        before = {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        context_for_vault(self.root, AS_OF)
        after = {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        self.assertEqual(before, after)

    def test_cli_clean_start_today_and_formal_record(self):
        with redirect_stdout(io.StringIO()):
            self.assertEqual(main(["init", "--vault", str(self.root), "--demo"]), 0)
            self.assertEqual(main(["course", "--vault", str(self.root), "--file", str(Path(__file__).resolve().parents[1] / "examples/courses/limits-and-recall.json")]), 0)
            self.assertEqual(main(["today", "--vault", str(self.root), "--as-of", AS_OF.isoformat()]), 0)
            self.assertEqual(main(["record", "--vault", str(self.root), "--summary", "Fictional independent answer",
                                   "--unit", MEMORY, "--question", "fictional-q", "--result", "correct",
                                   "--mode", "independent", "--activity", "recall", "--process", "clean",
                                   "--assistance", "0", "--occurred-at", "2026-08-01T09:00:00Z"]), 0)
        self.assertEqual(len(load_jsonl(self.root / "events/learning_events.jsonl")), 1)


if __name__ == "__main__":
    unittest.main()
