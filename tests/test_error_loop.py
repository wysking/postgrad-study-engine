from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.contracts import ContractError, append_event_atomic, load_jsonl, validate_knowledge_unit, validate_learning_event
from scripts.reducer import build_context_capsule, rebuild_state


UNIT = "math.calculus.limit.equivalent_substitution"


def attempt_event(
    event_id: str,
    timestamp: str,
    *,
    result: str = "correct",
    answer_mode: str = "independent",
    process_check: str = "clean",
    assistance_level: int = 0,
    activity: str = "solve",
    **attempt_overrides,
):
    attempt = {
        "question_id": "q-limit-001",
        "result": result,
        "answer_mode": answer_mode,
        "process_check": process_check,
        "assistance_level": assistance_level,
        "time_minutes": 8,
        **attempt_overrides,
    }
    return {
        "schema_version": "1.0",
        "event_id": event_id,
        "timestamp": timestamp,
        "event_type": "attempt",
        "subject": "math",
        "unit_ids": [UNIT],
        "activity": activity,
        "attempt": attempt,
    }


def diagnosis_event(event_id: str, timestamp: str, status: str, *, supersedes: str | None = None):
    diagnosis = {
        "diagnosis_id": "diag-limit-001",
        "question_id": "q-limit-001",
        "status": status,
        "generated_by": "joint",
        "confidence": 0.9,
        "first_divergence": "Replaced an additive term with an equivalent infinitesimal.",
        "root_cause": "Did not distinguish product substitution from additive substitution.",
        "error_tags": ["condition-check.equivalent-infinitesimal"],
        "evidence_refs": ["draft:line-3"],
    }
    if status == "confirmed":
        diagnosis.update({
            "learner_verdict": "Confirmed by checking the original draft.",
            "confirmation_method": "draft_check",
            "next_action": "Generate one isomorphic and one boundary variant.",
        })
    if supersedes:
        diagnosis["supersedes_event_id"] = supersedes
    return {
        "schema_version": "1.0",
        "event_id": event_id,
        "timestamp": timestamp,
        "event_type": "diagnosis",
        "subject": "math",
        "unit_ids": [UNIT],
        "diagnosis": diagnosis,
    }


class ContractTests(unittest.TestCase):
    def test_foundational_unit_may_have_no_prerequisites(self):
        unit = {
            "schema_version": "1.0",
            "unit_id": "math.calculus.limit.definition",
            "subject": "math",
            "title": "Limit definition",
            "prerequisites": [],
        }
        self.assertIs(validate_knowledge_unit(unit), unit)

    def test_independent_attempt_cannot_hide_assistance(self):
        event = attempt_event("e1", "2026-08-10T09:00:00+08:00", assistance_level=1)
        with self.assertRaisesRegex(ContractError, "independent attempt"):
            validate_learning_event(event)

    def test_invalid_or_duplicate_append_does_not_corrupt_ledger(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "events.jsonl"
            event = attempt_event("e1", "2026-08-10T09:00:00+08:00")
            append_event_atomic(ledger, event)
            before = ledger.read_bytes()
            with self.assertRaisesRegex(ContractError, "duplicate event_id"):
                append_event_atomic(ledger, event)
            self.assertEqual(ledger.read_bytes(), before)
            invalid = json.loads(json.dumps(event))
            invalid["event_id"] = "e2"
            invalid["unexpected"] = True
            with self.assertRaisesRegex(ContractError, "unsupported fields"):
                append_event_atomic(ledger, invalid)
            self.assertEqual(ledger.read_bytes(), before)
            self.assertEqual(len(load_jsonl(ledger)), 1)

    def test_diagnosis_revision_must_reference_same_diagnosis(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "events.jsonl"
            first = diagnosis_event("d1", "2026-08-10T09:00:00+08:00", "hypothesized")
            append_event_atomic(ledger, first)
            revision = diagnosis_event("d2", "2026-08-10T09:05:00+08:00", "confirmed", supersedes="missing")
            with self.assertRaisesRegex(ContractError, "latest revision"):
                append_event_atomic(ledger, revision)

    def test_repeated_diagnosis_requires_linear_revision_chain(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "events.jsonl"
            first = diagnosis_event("d1", "2026-08-10T09:00:00+08:00", "hypothesized")
            append_event_atomic(ledger, first)
            unlinked = diagnosis_event("d2", "2026-08-10T09:05:00+08:00", "confirmed")
            with self.assertRaisesRegex(ContractError, "requires supersedes_event_id"):
                append_event_atomic(ledger, unlinked)
            linked = diagnosis_event("d2", "2026-08-10T09:05:00+08:00", "confirmed", supersedes="d1")
            append_event_atomic(ledger, linked)
            stale = diagnosis_event("d3", "2026-08-10T09:10:00+08:00", "rejected", supersedes="d1")
            with self.assertRaisesRegex(ContractError, "latest revision"):
                append_event_atomic(ledger, stale)

    def test_full_ledger_validation_detects_manual_chain_corruption(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "events.jsonl"
            first = diagnosis_event("d1", "2026-08-10T09:00:00+08:00", "hypothesized")
            unlinked = diagnosis_event("d2", "2026-08-10T09:05:00+08:00", "confirmed")
            ledger.write_text(
                json.dumps(first) + "\n" + json.dumps(unlinked) + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ContractError, "requires supersedes_event_id"):
                load_jsonl(ledger)


class ReducerTests(unittest.TestCase):
    def test_clean_correct_is_lightweight_and_schedules_delayed_review(self):
        event = attempt_event("e1", "2026-08-10T09:00:00+08:00", confidence_before=0.9)
        state = rebuild_state([event])
        unit = state["units"][UNIT]
        self.assertEqual(unit["clean_independent_correct"], 1)
        self.assertEqual(unit["flagged_correct"], 0)
        self.assertGreater(unit["mastery"]["independent"], 0.5)
        self.assertEqual([task["task_type"] for task in state["review_queue"]], ["review"])

    def test_guessed_correct_does_not_raise_mastery_and_needs_diagnostic(self):
        event = attempt_event(
            "e1",
            "2026-08-10T09:00:00+08:00",
            answer_mode="guess",
            confidence_before=0.2,
        )
        state = rebuild_state([event])
        unit = state["units"][UNIT]
        self.assertEqual(unit["mastery"]["independent"], 0.5)
        self.assertEqual(unit["flagged_correct"], 1)
        self.assertEqual(state["review_queue"][0]["task_type"], "diagnostic")

    def test_only_latest_confirmed_diagnosis_counts_as_error(self):
        proposed = diagnosis_event("d1", "2026-08-10T09:00:00+08:00", "hypothesized")
        confirmed = diagnosis_event("d2", "2026-08-10T09:05:00+08:00", "confirmed", supersedes="d1")
        state = rebuild_state([proposed, confirmed])
        self.assertIn("condition-check.equivalent-infinitesimal", state["error_patterns"])
        self.assertEqual(state["review_queue"][0]["task_type"], "targeted_variant")

        rejected = diagnosis_event("d3", "2026-08-10T09:10:00+08:00", "rejected", supersedes="d2")
        state = rebuild_state([proposed, confirmed, rejected])
        self.assertEqual(state["error_patterns"], {})
        self.assertEqual(state["review_queue"], [])

    def test_clean_variant_resolves_targeted_variant_task(self):
        confirmed = diagnosis_event("d1", "2026-08-10T09:00:00+08:00", "confirmed")
        variant = attempt_event(
            "v1",
            "2026-08-10T09:30:00+08:00",
            activity="variant",
            variant_level="isomorphic",
            parent_diagnosis_id="diag-limit-001",
        )
        state = rebuild_state([confirmed, variant])
        self.assertNotIn("targeted_variant", [task["task_type"] for task in state["review_queue"]])
        self.assertIn("review", [task["task_type"] for task in state["review_queue"]])
        self.assertGreater(state["units"][UNIT]["mastery"]["transfer"], 0.5)

    def test_equal_timestamp_revision_keeps_ledger_order(self):
        timestamp = "2026-08-10T09:00:00+08:00"
        proposed = diagnosis_event("z-prior", timestamp, "hypothesized")
        confirmed = diagnosis_event("a-revision", timestamp, "confirmed", supersedes="z-prior")

        state = rebuild_state([proposed, confirmed])

        self.assertEqual(state["diagnoses"]["diag-limit-001"]["status"], "confirmed")
        self.assertIn("condition-check.equivalent-infinitesimal", state["error_patterns"])

    def test_unresolved_diagnoses_on_one_unit_remain_visible(self):
        diagnoses = []
        for index in range(3):
            item = diagnosis_event(f"d{index}", f"2026-08-10T09:0{index}:00+08:00", "hypothesized")
            item["diagnosis"]["diagnosis_id"] = f"diag-demo-{index}"
            item["diagnosis"]["next_action"] = f"Check fictional divergence {index}."
            diagnoses.append(item)

        state = rebuild_state(diagnoses)

        self.assertEqual(state["error_patterns"], {})
        self.assertEqual({task["diagnosis_id"] for task in state["review_queue"]}, {f"diag-demo-{index}" for index in range(3)})
        capsule = build_context_capsule(state)
        for index in range(3):
            self.assertIn(f"Check fictional divergence {index}.", capsule)

    def test_unrelated_success_does_not_close_another_diagnosis(self):
        proposed = diagnosis_event("d1", "2026-08-10T09:00:00+08:00", "hypothesized")
        unrelated = attempt_event("a1", "2026-08-10T09:30:00+08:00")
        state = rebuild_state([proposed, unrelated])
        self.assertIn("diag-limit-001", {task["diagnosis_id"] for task in state["review_queue"]})

        targeted = attempt_event("v1", "2026-08-10T09:30:00+08:00", activity="variant", parent_diagnosis_id="diag-limit-001")
        state = rebuild_state([proposed, targeted])
        self.assertNotIn("diag-limit-001", {task["diagnosis_id"] for task in state["review_queue"]})
        self.assertEqual(state["error_patterns"], {})

    def test_multi_unit_diagnosis_has_separate_completion_per_unit(self):
        other_unit = "math.calculus.limit.definition"
        confirmed = diagnosis_event("d1", "2026-08-10T09:00:00+08:00", "confirmed")
        confirmed["unit_ids"].append(other_unit)
        variant = attempt_event("v1", "2026-08-10T09:30:00+08:00", activity="variant", parent_diagnosis_id="diag-limit-001")

        initial = rebuild_state([confirmed])
        self.assertEqual(len(initial["review_queue"]), 2)
        state = rebuild_state([confirmed, variant])
        remaining = [task for task in state["review_queue"] if task["task_type"] == "targeted_variant"]
        self.assertEqual([task["unit_id"] for task in remaining], [other_unit])

    def test_closed_diagnosis_does_not_hide_a_later_failure_on_the_same_question(self):
        confirmed = diagnosis_event("d1", "2026-08-10T09:00:00+08:00", "confirmed")
        variant = attempt_event("v1", "2026-08-10T09:30:00+08:00", activity="variant", parent_diagnosis_id="diag-limit-001")
        recurrence = attempt_event("a2", "2026-08-11T09:00:00+08:00", result="incorrect")
        state = rebuild_state([confirmed, variant, recurrence])
        corrections = [task for task in state["review_queue"] if task["task_type"] == "correction"]
        self.assertEqual([task["source_event_id"] for task in corrections], ["a2"])

    def test_variant_before_equal_timestamp_revision_does_not_close_it(self):
        timestamp = "2026-08-10T09:00:00+08:00"
        proposed = diagnosis_event("d1", timestamp, "hypothesized")
        variant = attempt_event("v1", timestamp, activity="variant", parent_diagnosis_id="diag-limit-001")
        revision = diagnosis_event("d2", timestamp, "confirmed", supersedes="d1")
        state = rebuild_state([proposed, variant, revision])
        self.assertIn("targeted_variant", [task["task_type"] for task in state["review_queue"]])

    def test_state_rebuild_is_deterministic_and_capsule_is_compact(self):
        events = [
            attempt_event("e2", "2026-08-11T09:00:00+08:00", result="incorrect", confidence_before=0.9),
            attempt_event("e1", "2026-08-10T09:00:00+08:00"),
        ]
        first = rebuild_state(events)
        second = rebuild_state(list(reversed(events)))
        self.assertEqual(first, second)
        capsule = build_context_capsule(first)
        self.assertIn("Postgrad Codex Context Capsule", capsule)
        self.assertIn(UNIT, capsule)
        self.assertNotIn("q-limit-001", capsule)


if __name__ == "__main__":
    unittest.main()
