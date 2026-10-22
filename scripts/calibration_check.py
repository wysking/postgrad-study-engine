"""Reproducible synthetic parameter-recovery and held-out calibration check.

Known generating half-lives are fictional controls, not human calibration data.
No learner Vault, private events or restricted third-party dataset is accessed.
"""

from __future__ import annotations

import argparse
import math
import random
from datetime import datetime, timedelta, timezone
from statistics import median

from scripts.contracts import ContractError
from scripts.learning_models import (MODEL_VERSION, POLICY, digest, fit_half_life,
                                     memory_data, recall_prediction)
from scripts.reducer import load_units


def fictional_history(index: int, trials: int, seed: int) -> tuple[list[dict], dict, float]:
    rng = random.Random(seed + index)
    half_life = 0.75 * 2 ** (index % 6)
    uid = "english.recall.synthetic"
    unit = {"schema_version": "1.0", "unit_id": uid, "subject": "english",
            "title": "Fictional atomic recall control", "evidence_targets": ["recall", "delayed"]}
    at = datetime(2020, 1, 1, tzinfo=timezone.utc)
    events = []

    def event(result, delay=None):
        identifier = f"fictional-{index}-{len(events)}"
        attempt = {"question_id": "fictional-fixed-item", "result": result,
                   "answer_mode": "recalled", "process_check": "clean", "assistance_level": 0,
                   "evidence": "Synthetic observation from the declared known-half-life generator."}
        if delay is not None:
            attempt["delayed_days"] = delay
        events.append({"schema_version": "1.0", "event_id": identifier, "timestamp": at.isoformat(),
                       "event_type": "attempt", "subject": "english", "unit_ids": [uid],
                       "activity": "recall", "source_ref": "fictional:known-generating-law", "attempt": attempt})

    event("correct")
    for _ in range(trials):
        days = rng.choice([1, 2, 3, 7, 14, 21])
        at += timedelta(days=days)
        recalled = rng.random() < recall_prediction(days, half_life)
        event("correct" if recalled else "incorrect", days)
        if not recalled:
            # A simulated immediate successful restudy creates a new anchor.
            # It is explicit fixture evidence, not an inferred human success.
            at += timedelta(minutes=1)
            event("correct")
    return events, unit, half_life


def metrics(rows: list[dict], key: str) -> dict:
    n = len(rows)
    if not n:
        return {"count": 0, "brier": None, "log_loss": None, "binned_absolute_calibration_gap": None, "calibration_bins": []}
    bins = []
    for i in range(10):
        members = [r for r in rows if min(9, int(r[key] * 10)) == i]
        if members:
            bins.append({"count": len(members), "mean_prediction": sum(r[key] for r in members) / len(members),
                         "observed_recall": sum(r["recalled"] for r in members) / len(members)})
    return {"count": n, "brier": sum((r[key] - r["recalled"]) ** 2 for r in rows) / n,
            "log_loss": -sum(math.log(max(1e-12, min(1 - 1e-12, r[key] if r["recalled"] else 1 - r[key])))
                             for r in rows) / n,
            "binned_absolute_calibration_gap": sum(b["count"] * abs(b["mean_prediction"] - b["observed_recall"]) for b in bins) / n,
            "calibration_bins": bins}


def run_check(*, learners: int = 24, trials: int = 40, training_trials: int = 20,
              seed: int = 20261022) -> dict:
    if (type(learners) is not int or learners < 1 or type(trials) is not int
            or type(training_trials) is not int or not 2 <= training_trials < trials or type(seed) is not int):
        raise ContractError("synthetic check needs positive learners and 2 <= training_trials < trials")
    rows, parameters, sources, deltas = [], [], [], []
    for index in range(learners):
        events, unit, true_h = fictional_history(index, trials, seed)
        cutoff = datetime.fromisoformat(events[-1]["timestamp"])
        samples = memory_data(events, load_units([unit]), cutoff)["samples"]
        if len(samples) != trials:
            raise ContractError("synthetic fixture did not retain its declared sample count")
        train, held_out = samples[:training_trials], samples[training_trials:]
        fit = fit_half_life(train)
        lo, hi = fit["model_interval_90_days"]
        parameters.append({"true_half_life_days": true_h, "fitted_half_life_days": fit["half_life_days"],
                           "covered_by_conditional_interval": lo <= true_h <= hi})
        local = [{"recalled": s["recalled"],
                  "fitted": recall_prediction(s["elapsed_days"], fit["half_life_days"]),
                  "fixed_prior": recall_prediction(s["elapsed_days"], POLICY["prior_half_life_days"]),
                  "oracle": recall_prediction(s["elapsed_days"], true_h)} for s in held_out]
        rows.extend(local)
        deltas.append(metrics(local, "fitted")["brier"] - metrics(local, "fixed_prior")["brier"])
        sources.append(digest({"events": events, "unit": unit}))
    rng = random.Random(seed)
    bootstrap = sorted(sum(rng.choice(deltas) for _ in deltas) / len(deltas) for _ in range(1000))
    setup = {"learners": learners, "trials_per_learner": trials, "training_trials": training_trials,
             "seed": seed, "generating_half_lives_days": [0.75, 1.5, 3, 6, 12, 24],
             "intervals_days": [1, 2, 3, 7, 14, 21], "same_law_constant_half_life": True}
    return {"schema_version": "1.0", "report_id": digest({"setup": setup, "model_version": MODEL_VERSION}),
            "model_version": MODEL_VERSION, "data_kind": "synthetic_not_human_validation",
            "validation_status": "synthetic_sanity_only", "setup": setup, "source_hash": digest(sources),
            "evaluation": "fit_first_trials_freeze_parameters_score_later_trials_per_learner",
            "metrics": {key: metrics(rows, key) for key in ("fitted", "fixed_prior", "oracle")},
            "parameter_recovery": {"median_absolute_log_half_life_error": median(
                abs(math.log(p["fitted_half_life_days"] / p["true_half_life_days"])) for p in parameters),
                "conditional_interval_90_coverage": sum(p["covered_by_conditional_interval"] for p in parameters) / learners},
            "paired_brier_difference": {"mean_fitted_minus_fixed": sum(deltas) / len(deltas),
                                        "learner_bootstrap_95_interval": [bootstrap[24], bootstrap[974]],
                                        "bootstrap_draws": 1000},
            "limitations": ["Generated under the same functional law; no human calibration or transfer claim.",
                            "No policy or prior was tuned on this held-out report.",
                            "Synthetic interval coverage is not real-world interval coverage.",
                            "No inference about score gains, time savings or alternative real schedules."]}


def main(argv=None) -> int:
    import json
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--learners", type=int, default=24)
    p.add_argument("--trials", type=int, default=40)
    p.add_argument("--training-trials", type=int, default=20)
    p.add_argument("--seed", type=int, default=20261022)
    args = p.parse_args(argv)
    report = run_check(learners=args.learners, trials=args.trials, training_trials=args.training_trials, seed=args.seed)
    print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
