"""Fictional delayed confirmation eligibility, including mobile integration."""

from tests.fictional_release_vault import FictionalMobileVault, NEXT_DAY, START, external


class ConfirmationDueTests(FictionalMobileVault):
    def assisted_queue(self):
        self.register(["independent"])
        event = self.attempt(mode="assisted", assistance=1)
        event["timestamp"] = START
        self.call("record_attempt", {"event": event})
        task = self.state()["review_queue"][0]
        self.assertEqual(task["task_type"], "diagnostic")
        self.assertEqual(task["due_at"], NEXT_DAY)
        return task

    def test_derived_assisted_confirmation_waits_until_exact_due(self):
        task = self.assisted_queue()
        before = (self.root / "state/derived_state.json").read_bytes()
        early = self.schedule()
        self.assertEqual(early["selected_tasks"], [])
        self.assertIn({"task_id": task["task_id"], "reason": "check_not_due"}, early["excluded_candidates"])
        due = self.schedule(as_of=NEXT_DAY)
        self.assertEqual([t["task_id"] for t in due["selected_tasks"]], [task["task_id"]])
        self.assertEqual((self.root / "state/derived_state.json").read_bytes(), before)

    def test_equivalent_timezone_and_one_second_boundary(self):
        task = self.assisted_queue()
        self.assertEqual(self.schedule(as_of="2026-08-11T16:59:59+08:00")["selected_tasks"], [])
        due = self.schedule(as_of="2026-08-11T17:00:00+08:00")
        self.assertEqual([t["task_id"] for t in due["selected_tasks"]], [task["task_id"]])

    def test_early_practice_is_available_without_becoming_delayed_confirmation(self):
        task = self.assisted_queue()
        before = self.state()["review_queue"]
        result = self.schedule(candidates=[external(due_at=NEXT_DAY)])
        self.assertEqual([t["task_id"] for t in result["selected_tasks"]], ["fictional-external"])
        self.assertEqual(result["selected_tasks"][0]["task_type"], "practice")
        self.assertIn({"task_id": task["task_id"], "reason": "check_not_due"}, result["excluded_candidates"])
        self.assertEqual(self.state()["review_queue"], before)

    def test_external_future_checks_obey_the_same_gate(self):
        for kind in ("diagnostic", "correction", "targeted_variant"):
            with self.subTest(kind=kind):
                task = external(task_type=kind, due_at=NEXT_DAY)
                result = self.schedule(candidates=[task])
                self.assertEqual(result["selected_tasks"], [])
                self.assertEqual(result["excluded_candidates"], [
                    {"task_id": task["task_id"], "reason": "check_not_due"}])
                due = self.schedule(as_of=NEXT_DAY, candidates=[task])
                self.assertEqual([t["task_id"] for t in due["selected_tasks"]], [task["task_id"]])
