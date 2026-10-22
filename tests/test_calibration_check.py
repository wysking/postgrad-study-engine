"""Known-law fictional controls; these tests cannot establish human calibration."""

import copy
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.calibration_check import run_check
from scripts.contracts import ContractError
from scripts.learning_models import fit_half_life, memory_data


class SyntheticCalibrationTests(unittest.TestCase):
    def test_deterministic_report_has_declared_held_out_counts(self):
        report = run_check(learners=3, trials=10, training_trials=4)
        self.assertEqual(report, run_check(learners=3, trials=10, training_trials=4))
        self.assertEqual(report["data_kind"], "synthetic_not_human_validation")
        self.assertEqual(report["validation_status"], "synthetic_sanity_only")
        for metric in report["metrics"].values():
            self.assertEqual(metric["count"], 18)
            self.assertEqual(sum(b["count"] for b in metric["calibration_bins"]), 18)
            self.assertTrue(0 <= metric["brier"] <= 1)
            self.assertTrue(0 <= metric["binned_absolute_calibration_gap"] <= 1)

    def test_future_labels_never_enter_fitting(self):
        first_inputs, changed_inputs = [], []

        def capture(destination):
            def fit(samples):
                destination.append(copy.deepcopy(samples))
                return fit_half_life(samples)
            return fit

        def flip_future(*args):
            data = memory_data(*args)
            for sample in data["samples"][4:]:
                sample["recalled"] = 1 - sample["recalled"]
            return data

        with patch("scripts.calibration_check.fit_half_life", side_effect=capture(first_inputs)):
            original = run_check(learners=2, trials=10, training_trials=4)
        with patch("scripts.calibration_check.memory_data", side_effect=flip_future), patch(
                "scripts.calibration_check.fit_half_life", side_effect=capture(changed_inputs)):
            changed = run_check(learners=2, trials=10, training_trials=4)
        self.assertEqual(first_inputs, changed_inputs)
        self.assertTrue(all(len(samples) == 4 for samples in first_inputs))
        self.assertEqual(original["parameter_recovery"], changed["parameter_recovery"])
        self.assertNotEqual(original["metrics"], changed["metrics"])

    def test_published_summary_reproduces_without_private_inputs(self):
        expected = json.loads((Path(__file__).resolve().parents[1] /
                               "examples/calibration/synthetic_check.json").read_text(encoding="utf-8"))
        actual = run_check()
        self.assertEqual(actual["source_hash"], expected["source_hash"])
        self.assertEqual(actual["report_id"], expected["report_id"])
        for name in actual["metrics"]:
            self.assertEqual(actual["metrics"][name]["count"], expected["metrics"][name]["count"])
            for metric in ("brier", "log_loss", "binned_absolute_calibration_gap"):
                self.assertAlmostEqual(actual["metrics"][name][metric], expected["metrics"][name][metric], places=12)

    def test_invalid_configurations_fail(self):
        for config in ({"learners": True}, {"learners": 0}, {"training_trials": 1},
                       {"training_trials": 40}, {"trials": 2}, {"seed": False}):
            with self.subTest(config=config), self.assertRaises(ContractError):
                run_check(**config)
