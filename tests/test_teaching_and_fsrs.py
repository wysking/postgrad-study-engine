"""Offline transport controls plus optional real py-fsrs integration."""

import copy
import io
import json
import os
import tempfile
import unittest
from importlib.util import find_spec
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

from scripts.contracts import ContractError
from scripts.fsrs_adapter import fsrs_report
from scripts.learning_context import context_for_vault
from scripts.study import init_vault, install_course
from scripts.teaching import offline_teach, openai_teach, response_text
from tests.test_learning_models import AS_OF, COURSE, EVENTS, MEMORY


class TeachingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "fictional"
        init_vault(self.root, demo=True)
        install_course(self.root, COURSE)
        self.context = context_for_vault(self.root, AS_OF)

    def test_offline_teaching_has_no_evidence_side_effect(self):
        before = context_for_vault(self.root, AS_OF)
        text = offline_teach(self.context, "Fictional learner asks for a hint")
        self.assertIn("Offline reference", text)
        self.assertEqual(before, context_for_vault(self.root, AS_OF))

    def test_responses_transport_uses_explicit_model_and_omits_raw_history(self):
        seen = {}

        def transport(req, timeout):
            seen["url"], seen["payload"] = req.full_url, json.loads(req.data)
            return io.StringIO(json.dumps({"status": "completed", "output": [
                {"type": "reasoning", "summary": []},
                {"type": "message", "content": [{"type": "output_text", "text": "Fictional graded hint"}]}]}))

        with patch.dict(os.environ, {"OPENAI_API_KEY": "fictional-test-key"}):
            text = openai_teach(self.context, "Fictional question", "fictional-configured-model", transport=transport)
        self.assertEqual(text, "Fictional graded hint")
        self.assertEqual(seen["url"], "https://api.openai.com/v1/responses")
        self.assertFalse(seen["payload"]["store"])
        self.assertEqual(seen["payload"]["model"], "fictional-configured-model")
        data = json.loads(seen["payload"]["input"])
        self.assertNotIn("learner", data)
        self.assertNotIn("state", data)
        self.assertNotIn("messages", data)

    def test_missing_key_or_model_is_an_explicit_error(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ContractError):
                openai_teach(self.context, "Fictional question", "fictional-model")
        with self.assertRaises(ContractError):
            openai_teach(self.context, "Fictional question", "")

    def test_incomplete_refused_and_empty_responses_do_not_look_successful(self):
        for response in ({"status": "incomplete"}, {"status": "completed", "output": []},
                         {"status": "completed", "output": [{"type": "message", "content": [{"type": "refusal"}]}]}):
            with self.assertRaises(ContractError):
                response_text(response)

    def test_malformed_responses_fail_as_contract_errors(self):
        for output in (None, {}, [None], [{"type": "message", "content": None}],
                       [{"type": "message", "content": [None]}]):
            with self.subTest(output=output), self.assertRaises(ContractError):
                response_text({"status": "completed", "output": output})

    def test_api_error_never_echoes_private_body_or_credentials(self):
        def transport(req, timeout):
            raise HTTPError(req.full_url, 429, "fictional-private-error", {}, io.BytesIO(b"fictional-private-body"))
        with patch.dict(os.environ, {"OPENAI_API_KEY": "fictional-secret"}):
            with self.assertRaises(ContractError) as caught:
                openai_teach(self.context, "Fictional question", "fictional-model", transport=transport)
        self.assertIn("429", str(caught.exception))
        self.assertNotIn("secret", str(caught.exception))
        self.assertNotIn("private", str(caught.exception))


class FsrsAdapterTests(unittest.TestCase):
    def setUp(self):
        self.events = copy.deepcopy([e for e in EVENTS if e["unit_ids"] == [MEMORY]])
        self.ratings = {"schema_version": "1.0", "learner_id": "fictional-a", "ratings": [
            {"event_id": e["event_id"], "rating": 1 if e["attempt"]["result"] == "incorrect" else 3,
             "source": "observed"} for e in self.events]}

    def run_report(self, events=None, ratings=None, cutoff=AS_OF):
        return fsrs_report(self.events if events is None else events, COURSE["units"],
                           self.ratings if ratings is None else ratings, cutoff, "fictional-a")

    def test_conflicting_rating_and_cross_learner_input_are_rejected(self):
        r = copy.deepcopy(self.ratings)
        r["ratings"][-1]["rating"] = 3
        with self.assertRaises(ContractError):
            self.run_report(ratings=r)
        r = copy.deepcopy(self.ratings)
        r["learner_id"] = "fictional-other"
        with self.assertRaises(ContractError):
            self.run_report(ratings=r)

    def test_missing_intervening_rating_does_not_invent_long_interval(self):
        r = copy.deepcopy(self.ratings)
        r["ratings"].pop(1)
        with self.assertRaises(ContractError):
            self.run_report(ratings=r)

    def test_archived_units_are_not_fsrs_cards(self):
        units = copy.deepcopy(COURSE["units"])
        next(u for u in units if u["unit_id"] == MEMORY)["status"] = "archived"
        with self.assertRaises(ContractError):
            fsrs_report(self.events, units, self.ratings, AS_OF, "fictional-a")

    def test_boolean_and_duplicate_ratings_are_rejected(self):
        r = copy.deepcopy(self.ratings)
        r["ratings"][0]["rating"] = True
        with self.assertRaises(ContractError):
            self.run_report(ratings=r)
        r = copy.deepcopy(self.ratings)
        r["ratings"].append(r["ratings"][0])
        with self.assertRaises(ContractError):
            self.run_report(ratings=r)

    @unittest.skipUnless(find_spec("fsrs"), "optional fsrs==6.3.2 is not installed")
    def test_real_library_is_deterministic_with_fuzzing_disabled(self):
        first = self.run_report()
        self.assertEqual(first, self.run_report())
        self.assertEqual(first["sample_count"], 3)
        self.assertEqual(first["status"], "library_default_parameters")
        self.assertTrue(0 <= first["brier"] <= 1)
        self.assertIn(MEMORY, first["cards"])

    @unittest.skipUnless(find_spec("fsrs"), "optional fsrs==6.3.2 is not installed")
    def test_future_reviews_do_not_change_past_fsrs_prediction(self):
        from datetime import datetime, timezone
        cutoff = datetime(2026, 8, 4, 9, tzinfo=timezone.utc)
        subset = self.events[:2]
        r = copy.deepcopy(self.ratings)
        r["ratings"] = r["ratings"][:2]
        self.assertEqual(self.run_report(cutoff=cutoff), self.run_report(subset, r, cutoff))


if __name__ == "__main__":
    unittest.main()
