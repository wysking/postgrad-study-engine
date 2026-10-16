"""Fictional registered subject identity cannot be relabeled by a candidate."""

from tests.fictional_release_vault import ACTIVATION, FictionalMobileVault, external


class SubjectIdentityTests(FictionalMobileVault):
    def test_math_unit_cannot_count_as_english(self):
        self.register(["independent"])
        result = self.schedule(phase_subjects=["english"], candidates=[external(subject="english")])
        self.assertEqual(result["selected_tasks"], [])
        self.assertEqual(result["subject_minutes"], {})
        self.assertIn({"task_id": "fictional-external", "reason": "unit_subject_mismatch"},
                      result["excluded_candidates"])

    def test_contest_cannot_bypass_activation_by_math_label(self):
        unit_id = "math_contest.fictional.release_check"
        self.register(["independent"], "math_contest", unit_id)
        result = self.schedule(phase_subjects=["math", "math_contest"], candidates=[
            external(subject="math", unit_id=unit_id)])
        self.assertEqual(result["selected_tasks"], [])
        self.assertIn({"task_id": "fictional-external", "reason": "unit_subject_mismatch"},
                      result["excluded_candidates"])

    def test_matching_contest_waits_for_activation_then_becomes_eligible(self):
        unit_id = "math_contest.fictional.release_check"
        self.register(["independent"], "math_contest", unit_id)
        task = external(subject="math_contest", unit_id=unit_id)
        self.assertEqual(self.schedule(phase_subjects=["math_contest"], candidates=[task])["selected_tasks"], [])
        due = self.schedule(as_of=ACTIVATION, phase_subjects=["math_contest"], candidates=[task])
        self.assertIn("fictional-external", [t["task_id"] for t in due["selected_tasks"]])
        self.assertEqual(due["subject_minutes"], {"math_contest": 20})

    def test_matching_registered_subject_remains_eligible(self):
        self.register(["independent"])
        result = self.schedule(candidates=[external()])
        self.assertIn("fictional-external", [t["task_id"] for t in result["selected_tasks"]])
        self.assertEqual(result["subject_minutes"], {"math": 20})

    def test_unknown_external_unit_retains_caller_qualification_boundary(self):
        result = self.schedule(phase_subjects=["english"], candidates=[
            external(subject="english", unit_id="english.fictional.unknown")])
        self.assertEqual([t["task_id"] for t in result["selected_tasks"]], ["fictional-external"])
        self.assertEqual(result["subject_minutes"], {"english": 10})
