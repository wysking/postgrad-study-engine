"""Experimental, rebuildable learning models. Never modify assessed evidence.

Half-life estimates concern qualified atomic recall only. Skill risk describes
the observed task mix, not general ability. Neither output is calibrated.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from datetime import datetime
from typing import Any

from scripts.contracts import ContractError, parse_datetime, validate_event_sequence
from scripts.reducer import SOLVING_ACTIVITIES, load_units

MODEL_VERSION = "learning-models-0.1"
POLICY = {"prior_half_life_days": 3.0, "log_prior_sigma": math.log(2),
          "minimum_half_life_days": 0.125, "maximum_half_life_days": 365.0,
          "grid_points": 181, "minimum_elapsed_days": 1.0}


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def observed_by(events: list[dict], cutoff: datetime) -> list[dict]:
    """Apply the cutoff before deriving states, labels or revision chains."""
    if cutoff.tzinfo is None or cutoff.utcoffset() is None:
        raise ContractError("cutoff must have a timezone")
    included = [e for e in events if parse_datetime(e["timestamp"]) <= cutoff]
    validate_event_sequence(included)
    return sorted(included, key=lambda e: parse_datetime(e["timestamp"]))


def unassisted_observation(event: dict) -> bool:
    a = event["attempt"]
    return (a["answer_mode"] in {"independent", "recalled"}
            and a["assistance_level"] == 0 and a["process_check"] == "clean"
            and a["result"] in {"correct", "incorrect"})


def memory_data(events: list[dict], registry: dict, cutoff: datetime) -> dict:
    """Require a clear successful anchor and an explicitly observed delay.

    Any intervening assessed activity on the item breaks the old anchor; a new
    qualified correct retrieval can establish a new one. Unknown exposures
    outside the ledger remain a limitation, not fabricated observations.
    """
    samples, excluded, anchors = [], [], {}
    memory_units = {uid for uid, u in registry.items()
                    if u.get("status", "active") == "active"
                    and "recall" in u.get("evidence_targets", [])
                    and not set(u["evidence_targets"]) & {"independent", "transfer", "timed"}}
    for e in observed_by(events, cutoff):
        if e["event_type"] != "attempt":
            continue
        units = e["unit_ids"]
        relevant = [uid for uid in units if uid in memory_units]
        if not relevant:
            excluded.append({"event_id": e["event_id"], "reason": "outside_atomic_recall_domain"})
            continue
        old = {uid: anchors.pop(uid, None) for uid in relevant}
        reason = None
        if len(units) != 1:
            reason = "multiple_units_are_not_independent_retrieval_samples"
        elif e["subject"] != registry[units[0]]["subject"]:
            raise ContractError("memory event and registered subject disagree")
        elif e["activity"] not in {"recall", "review"} or not unassisted_observation(e):
            reason = "unqualified_or_intervening_activity"
        else:
            uid = units[0]
            a, anchor = e["attempt"], old[uid]
            if anchor is None:
                reason = "no_qualified_successful_anchor"
            else:
                days = (parse_datetime(e["timestamp"]) - parse_datetime(anchor["timestamp"])).total_seconds() / 86400
                declared = a.get("delayed_days")
                if declared is None or declared < 1:
                    reason = "delay_not_explicitly_observed"
                elif days < POLICY["minimum_elapsed_days"] or abs(days - declared) >= 1:
                    reason = "delay_conflicts_with_anchor_timestamps"
                else:
                    samples.append({"event_id": e["event_id"], "anchor_event_id": anchor["event_id"],
                                    "unit_id": uid, "timestamp": e["timestamp"],
                                    "elapsed_days": days, "recalled": int(a["result"] == "correct")})
            if a["result"] == "correct":
                anchors[uid] = {"event_id": e["event_id"], "timestamp": e["timestamp"]}
        if reason:
            excluded.append({"event_id": e["event_id"], "reason": reason})
    return {"samples": samples, "excluded": excluded, "anchors": anchors,
            "memory_unit_ids": sorted(memory_units)}


def recall_prediction(days: float, half_life: float) -> float:
    if not math.isfinite(days) or days < 0 or not math.isfinite(half_life) or half_life <= 0:
        raise ContractError("elapsed days must be finite/nonnegative and half-life finite/positive")
    return math.exp(-math.log(2) * days / half_life)


def fit_half_life(samples: list[dict]) -> dict:
    """Bounded grid MAP with an explicit log-normal regularizing prior.

    The interval is conditional on this model/prior/grid, not an empirical
    calibration certificate or confidence about a learner's overall mastery.
    """
    p = POLICY
    low, high = math.log(p["minimum_half_life_days"]), math.log(p["maximum_half_life_days"])
    logs = [low + (high - low) * i / (p["grid_points"] - 1) for i in range(p["grid_points"])]
    logs = sorted(set(logs + [math.log(p["prior_half_life_days"])]))
    losses = []
    for log_h in logs:
        loss = 0.5 * ((log_h - math.log(p["prior_half_life_days"])) / p["log_prior_sigma"]) ** 2
        for s in samples:
            probability = min(1 - 1e-12, max(1e-12, recall_prediction(s["elapsed_days"], math.exp(log_h))))
            loss -= math.log(probability if s["recalled"] else 1 - probability)
        losses.append(loss)
    best = min(range(len(logs)), key=lambda i: (losses[i], i))
    weights = [math.exp(min(losses) - value) for value in losses]
    total = sum(weights)

    def quantile(q):
        cumulative = 0.0
        for log_h, weight in zip(logs, weights):
            cumulative += weight / total
            if cumulative >= q:
                return math.exp(log_h)
        return math.exp(logs[-1])

    return {"status": "fitted_uncalibrated" if samples else "prior_only",
            "sample_count": len(samples), "half_life_days": math.exp(logs[best]),
            "model_interval_90_days": [quantile(0.05), quantile(0.95)],
            "interval_kind": "conditional_grid_posterior_not_calibrated",
            "fit_method": "bounded_log_half_life_grid_MAP", "at_parameter_bound": best in {0, len(logs) - 1},
            "source_event_ids": [s["event_id"] for s in samples]}


def skill_risks(events: list[dict], registry: dict, cutoff: datetime) -> dict:
    """Beta(1,1)-smoothed failure estimates on qualified observed solve tasks.

    Count a multi-unit task once as an excluded attribution, not once per unit.
    Unknown process/assistance and missing tags are never negative labels.
    """
    counts = {uid: {"correct": 0, "incorrect": 0, "source_event_ids": []} for uid in registry}
    for e in observed_by(events, cutoff):
        if (e["event_type"] != "attempt" or len(e["unit_ids"]) != 1
                or e["activity"] not in SOLVING_ACTIVITIES or not unassisted_observation(e)
                or e["attempt"]["answer_mode"] != "independent"):
            continue
        uid = e["unit_ids"][0]
        if uid not in counts:
            continue
        if e["subject"] != registry[uid]["subject"]:
            raise ContractError("skill event and registered subject disagree")
        counts[uid][e["attempt"]["result"]] += 1
        counts[uid]["source_event_ids"].append(e["event_id"])
    for c in counts.values():
        n = c["correct"] + c["incorrect"]
        c.update({"sample_count": n, "estimated_failure_on_observed_task_mix": (c["incorrect"] + 1) / (n + 2),
                  "status": "fitted_uncalibrated" if n else "prior_only",
                  "scope": "observed_task_mix_not_general_ability_or_error_tag_probability"})
    return counts


def fit_models(events: list[dict], units: Any, cutoff: datetime, learner_id: str) -> dict:
    if not isinstance(learner_id, str) or not learner_id.strip():
        raise ContractError("learner_id is required")
    registry = load_units(units)
    included = observed_by(events, cutoff)
    data = memory_data(included, registry, cutoff)
    memory = {}
    for uid in data["memory_unit_ids"]:
        fit = fit_half_life([s for s in data["samples"] if s["unit_id"] == uid])
        anchor = data["anchors"].get(uid)
        elapsed = (cutoff - parse_datetime(anchor["timestamp"])).total_seconds() / 86400 if anchor else None
        fit.update({"anchor": anchor, "elapsed_days": elapsed,
                    "predicted_recall": recall_prediction(elapsed, fit["half_life_days"]) if anchor else None,
                    "curve_if_recalled_now": [{"days": d, "predicted_recall": recall_prediction(d, fit["half_life_days"])}
                                              for d in (1, 3, 7, 14)]})
        memory[uid] = fit
    source_hash = digest({"events": included, "registry": registry, "cutoff": cutoff.isoformat(), "policy": POLICY})
    return {"schema_version": "1.0", "model_version": MODEL_VERSION,
            "model_id": digest({"learner_id": learner_id, "source_hash": source_hash, "version": MODEL_VERSION}),
            "learner_id": learner_id, "training_cutoff": cutoff.isoformat(), "source_hash": source_hash,
            "policy": dict(POLICY), "calibration_status": "not_validated", "memory": memory,
            "skill_risks": skill_risks(included, registry, cutoff),
            "sample_audit": {"included": data["samples"], "excluded": data["excluded"]},
            "limitations": ["Unlogged study/exposure is unknown.", "No causal learning-effect or score-gain claim.",
                            "Model estimates are not mastery declarations; no scheduling weights are changed."]}


def evaluate_memory(events: list[dict], units: Any, cutoff: datetime) -> dict:
    """Predict each timestamp group using strictly earlier eligible outcomes."""
    data = memory_data(events, load_units(units), cutoff)
    past, predictions = [], []
    groups = {}
    for sample in data["samples"]:
        groups.setdefault(parse_datetime(sample["timestamp"]), []).append(sample)
    for timestamp, group in sorted(groups.items()):
        for s in group:
            fit = fit_half_life([p for p in past if p["unit_id"] == s["unit_id"]])
            predictions.append({**s, "fit_samples_before_prediction": fit["sample_count"],
                                "model": recall_prediction(s["elapsed_days"], fit["half_life_days"]),
                                "fixed_half_life": recall_prediction(s["elapsed_days"], POLICY["prior_half_life_days"]),
                                "constant": 0.5})
        past.extend(group)
    metrics = {}
    for name in ("model", "fixed_half_life", "constant"):
        if not predictions:
            metrics[name] = {"brier": None, "log_loss": None, "calibration_bins": []}
            continue
        bins = []
        for i in range(5):
            rows = [p for p in predictions if min(4, int(p[name] * 5)) == i]
            if rows:
                bins.append({"count": len(rows), "mean_prediction": sum(p[name] for p in rows) / len(rows),
                             "observed_recall": sum(p["recalled"] for p in rows) / len(rows)})
        metrics[name] = {"brier": sum((p[name] - p["recalled"]) ** 2 for p in predictions) / len(predictions),
                         "log_loss": -sum(math.log(max(1e-12, min(1 - 1e-12, p[name] if p["recalled"] else 1 - p[name])))
                                          for p in predictions) / len(predictions), "calibration_bins": bins}
    return {"schema_version": "1.0", "model_version": MODEL_VERSION, "as_of": cutoff.isoformat(),
            "method": "prequential_strict_timestamp_groups", "sample_count": len(predictions),
            "metrics": metrics, "predictions": predictions,
            "exclusion_counts": dict(Counter(x["reason"] for x in data["excluded"])),
            "validation_status": "descriptive_only_not_validated",
            "limitations": ["Historical replay tests prediction on observed reviews, not a counterfactual schedule.",
                            "Small bins and fictional data do not establish calibration or learning effectiveness."]}
