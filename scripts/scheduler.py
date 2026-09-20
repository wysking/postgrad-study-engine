"""Transparent constrained scheduler for work across all exam subjects."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from scripts.contracts import ACTIVITIES, SUBJECTS, ContractError, parse_datetime


SCHEDULER_MODEL_VERSION = "constrained-priority-0.1"
TASK_TYPES = {"learn", "practice", "review", "diagnostic", "correction", "targeted_variant", "timed_practice"}


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def _number(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise ContractError("scheduler metrics must be finite numbers")
    return float(value)


def _subject_activation(config: dict[str, Any], subject: str) -> datetime | None:
    activation = config.get("subject_activation", {}).get(subject)
    if activation is None:
        return None
    return parse_datetime(activation, f"config.subject_activation.{subject}")


def validate_scheduler_request(request: Any) -> dict[str, Any]:
    if not isinstance(request, dict):
        raise ContractError("scheduler request must be an object")
    allowed = {
        "schema_version", "available_minutes", "as_of", "fatigue_budget", "max_subject_share",
        "phase_subjects", "candidates",
    }
    extra = sorted(set(request) - allowed)
    if extra:
        raise ContractError(f"scheduler request has unsupported fields: {', '.join(extra)}")
    if request.get("schema_version") != "1.0":
        raise ContractError("scheduler request schema_version must be '1.0'")
    minutes = request.get("available_minutes")
    if not isinstance(minutes, int) or isinstance(minutes, bool) or minutes < 1:
        raise ContractError("available_minutes must be an integer >= 1")
    if "as_of" not in request:
        raise ContractError("scheduler request requires as_of for reproducible due-date decisions")
    parse_datetime(request["as_of"], "scheduler_request.as_of")
    if "fatigue_budget" in request and _number(request["fatigue_budget"]) < 0:
        raise ContractError("fatigue_budget must be >= 0")
    if "max_subject_share" in request and not 0 < _number(request["max_subject_share"]) <= 1:
        raise ContractError("max_subject_share must be in (0, 1]")
    if "phase_subjects" in request:
        if not isinstance(request["phase_subjects"], list) or not request["phase_subjects"]:
            raise ContractError("phase_subjects must be a non-empty array")
        if len(request["phase_subjects"]) != len(set(request["phase_subjects"])):
            raise ContractError("phase_subjects must not contain duplicates")
        if any(subject not in SUBJECTS for subject in request["phase_subjects"]):
            raise ContractError("phase_subjects contains an unknown subject")
    if "candidates" in request and not isinstance(request["candidates"], list):
        raise ContractError("candidates must be an array")
    for candidate in request.get("candidates", []):
        validate_candidate(candidate)
    return request


def validate_candidate(candidate: Any) -> dict[str, Any]:
    if not isinstance(candidate, dict):
        raise ContractError("candidate must be an object")
    required = {"task_id", "subject", "estimated_minutes"}
    missing = sorted(required - set(candidate))
    if missing:
        raise ContractError(f"candidate missing required fields: {', '.join(missing)}")
    if not isinstance(candidate["task_id"], str) or not candidate["task_id"].strip():
        raise ContractError("candidate.task_id must be non-empty")
    if candidate["subject"] not in SUBJECTS:
        raise ContractError("candidate.subject is unknown")
    if not isinstance(candidate["estimated_minutes"], int) or isinstance(candidate["estimated_minutes"], bool) or candidate["estimated_minutes"] < 1:
        raise ContractError("candidate.estimated_minutes must be an integer >= 1")
    if candidate.get("task_type", "practice") not in TASK_TYPES:
        raise ContractError("candidate.task_type is unknown")
    if candidate.get("activity", "solve") not in ACTIVITIES:
        raise ContractError("candidate.activity is unknown")
    for key in (
        "expected_score_gain", "forgetting_risk", "information_gain", "transfer_value",
        "urgency", "error_recurrence", "fatigue_cost",
    ):
        if key in candidate and _number(candidate[key]) < 0:
            raise ContractError(f"candidate.{key} must be >= 0")
    if "due_at" in candidate:
        parse_datetime(candidate["due_at"], "candidate.due_at")
    return candidate


def _recurrence_for_task(task: dict[str, Any], state: dict[str, Any]) -> float:
    counts = [state.get("error_patterns", {}).get(tag, {}).get("count", 0) for tag in task.get("error_tags", [])]
    if not counts:
        return 0.0
    return _clamp(max(counts) / 3.0)


def candidates_from_state(state: dict[str, Any], as_of: datetime, config: dict[str, Any]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    queued_units: set[str] = set()
    for task in state.get("review_queue", []):
        candidate = dict(task)
        unit = state.get("units", {}).get(task["unit_id"], {})
        due = parse_datetime(task["due_at"], "review_queue.due_at")
        days_overdue = max(0.0, (as_of - due).total_seconds() / 86400.0)
        days_until = max(0.0, (due - as_of).total_seconds() / 86400.0)
        mastery = unit.get("mastery_overall")
        mastery_gap = 0.65 if mastery is None else 1.0 - float(mastery)
        task_type = task["task_type"]
        candidate.update({
            "task_type": task_type,
            "expected_score_gain": float(unit.get("exam_weight", 0.5)) * _clamp(mastery_gap),
            "forgetting_risk": _clamp(0.5 + days_overdue / 14.0) if due <= as_of else _clamp(0.5 - days_until / 30.0),
            "information_gain": {"diagnostic": 1.0, "correction": 0.75, "targeted_variant": 0.85, "review": 0.4}.get(task_type, 0.4),
            "transfer_value": 0.8 if task_type == "targeted_variant" else 0.45,
            "urgency": _clamp(0.5 + days_overdue / 7.0) if due <= as_of else _clamp(0.4 - days_until / 30.0),
            "error_recurrence": _recurrence_for_task(task, state),
            "fatigue_cost": _clamp(float(task.get("estimated_minutes", 20)) / 90.0),
            "prerequisite_ready": True,
            "reason": task.get("reason", "derived review task"),
        })
        candidates.append(candidate)
        queued_units.add(task["unit_id"])

    threshold = float(config.get("prerequisite_threshold", 0.55))
    mastery_target = float(config.get("mastery_target", 0.75))
    for unit_id, unit in sorted(state.get("units", {}).items()):
        if unit_id in queued_units:
            continue
        prerequisites = unit.get("prerequisites", [])
        ready = all(
            state.get("units", {}).get(prerequisite, {}).get("mastery_overall") is not None
            and float(state["units"][prerequisite]["mastery_overall"]) >= threshold
            for prerequisite in prerequisites
        )
        attempts = int(unit.get("attempts", {}).get("total", 0))
        mastery = unit.get("mastery_overall")
        if attempts == 0:
            task_type = "learn"
            activity = "learn"
            gap = 0.75
            information_gain = 0.65
            reason = "unmeasured active knowledge unit"
        elif mastery is not None and float(mastery) < mastery_target:
            task_type = "practice"
            activity = "solve"
            gap = 1.0 - float(mastery)
            information_gain = 0.55
            reason = "mastery evidence remains below target"
        else:
            continue
        candidates.append({
            "task_id": f"{task_type}:{unit_id}",
            "task_type": task_type,
            "subject": unit["subject"],
            "unit_id": unit_id,
            "activity": activity,
            "estimated_minutes": int(unit.get("estimated_minutes", 20)),
            "expected_score_gain": float(unit.get("exam_weight", 0.5)) * gap,
            "forgetting_risk": 0.0,
            "information_gain": information_gain,
            "transfer_value": 0.35,
            "urgency": 0.15,
            "error_recurrence": 0.0,
            "fatigue_cost": _clamp(float(unit.get("estimated_minutes", 20)) / 75.0),
            "prerequisite_ready": ready,
            "reason": reason,
        })
    return candidates


def _score_candidate(candidate: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    weights = config["weights"]
    subject_weight = float(config.get("subject_weights", {}).get(candidate["subject"], 1.0))
    components = {
        key: _number(candidate.get(key, 0.0)) * float(weights[key])
        for key in (
            "expected_score_gain", "forgetting_risk", "information_gain", "transfer_value",
            "urgency", "error_recurrence",
        )
    }
    positive = sum(components.values()) * subject_weight
    duration_penalty = math.sqrt(max(candidate["estimated_minutes"] / 30.0, 0.5))
    fatigue_penalty = _number(candidate.get("fatigue_cost", 0.0)) * float(weights["fatigue_cost"])
    total = positive / duration_penalty - fatigue_penalty
    return {
        "components": {key: round(value, 6) for key, value in components.items()},
        "subject_weight": subject_weight,
        "duration_penalty": round(duration_penalty, 6),
        "fatigue_penalty": round(fatigue_penalty, 6),
        "total": round(total, 6),
    }


@dataclass(frozen=True)
class _Selection:
    score: float
    indices: tuple[int, ...]
    minutes: int
    fatigue_units: int
    subject_minutes: tuple[int, ...]


def _select_constrained(
    candidates: list[dict[str, Any]],
    available_minutes: int,
    max_subject_share: float,
    fatigue_budget: float | None,
    beam_limit: int,
) -> tuple[int, ...]:
    subjects = sorted({candidate["subject"] for candidate in candidates})
    subject_index = {subject: index for index, subject in enumerate(subjects)}
    cap = available_minutes if len(subjects) <= 1 else max(1, math.ceil(available_minutes * max_subject_share))
    fatigue_cap = None if fatigue_budget is None else round(fatigue_budget * 100)
    start = _Selection(0.0, (), 0, 0, tuple(0 for _ in subjects))
    states: dict[tuple[int, int, tuple[int, ...]], _Selection] = {(0, 0, start.subject_minutes): start}
    for index, candidate in enumerate(candidates):
        additions: dict[tuple[int, int, tuple[int, ...]], _Selection] = {}
        duration = candidate["estimated_minutes"]
        fatigue = round(_number(candidate.get("fatigue_cost", 0.0)) * 100)
        score = candidate["score_breakdown"]["total"]
        for state in states.values():
            minutes = state.minutes + duration
            fatigue_units = state.fatigue_units + fatigue
            if minutes > available_minutes or (fatigue_cap is not None and fatigue_units > fatigue_cap):
                continue
            subject_minutes = list(state.subject_minutes)
            position = subject_index[candidate["subject"]]
            subject_minutes[position] += duration
            if subject_minutes[position] > cap:
                continue
            subject_tuple = tuple(subject_minutes)
            selection = _Selection(state.score + score, state.indices + (index,), minutes, fatigue_units, subject_tuple)
            key = (minutes, fatigue_units, subject_tuple)
            current = additions.get(key) or states.get(key)
            if current is None or (selection.score, tuple(-i for i in selection.indices)) > (current.score, tuple(-i for i in current.indices)):
                additions[key] = selection
        states.update(additions)
        if len(states) > beam_limit:
            best = sorted(states.values(), key=lambda item: (-item.score, -item.minutes, item.indices))[:beam_limit]
            states = {(item.minutes, item.fatigue_units, item.subject_minutes): item for item in best}
    chosen = max(states.values(), key=lambda item: (item.score, item.minutes, tuple(-i for i in item.indices)))
    return chosen.indices


def build_schedule(state: dict[str, Any], request: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    validate_scheduler_request(request)
    as_of = parse_datetime(request["as_of"], "scheduler.as_of")
    phase_subjects = set(request.get("phase_subjects", config.get("phase_subjects", sorted(SUBJECTS))))
    max_subject_share = float(request.get("max_subject_share", config.get("max_subject_share", 1.0)))
    fatigue_budget = request.get("fatigue_budget")
    candidates = candidates_from_state(state, as_of, config) + [dict(item) for item in request.get("candidates", [])]
    seen: set[str] = set()
    eligible: list[dict[str, Any]] = []
    excluded: list[dict[str, str]] = []
    for candidate in sorted(candidates, key=lambda item: item["task_id"]):
        validate_candidate(candidate)
        task_id = candidate["task_id"]
        if task_id in seen:
            raise ContractError(f"duplicate scheduler candidate task_id: {task_id}")
        seen.add(task_id)
        if candidate["subject"] not in phase_subjects:
            excluded.append({"task_id": task_id, "reason": "subject_not_in_phase"})
            continue
        activation = _subject_activation(config, candidate["subject"])
        if activation is not None and as_of < activation:
            excluded.append({"task_id": task_id, "reason": "subject_not_active"})
            continue
        if candidate.get("prerequisite_ready", True) is not True:
            excluded.append({"task_id": task_id, "reason": "prerequisite_not_ready"})
            continue
        if candidate["estimated_minutes"] > request["available_minutes"]:
            excluded.append({"task_id": task_id, "reason": "exceeds_session_budget"})
            continue
        candidate["score_breakdown"] = _score_candidate(candidate, config)
        if candidate["score_breakdown"]["total"] <= 0:
            excluded.append({"task_id": task_id, "reason": "non_positive_value"})
            continue
        eligible.append(candidate)

    chosen_indices = _select_constrained(
        eligible,
        request["available_minutes"],
        max_subject_share,
        float(fatigue_budget) if fatigue_budget is not None else None,
        int(config.get("beam_limit", 20000)),
    )
    chosen_ids = {eligible[index]["task_id"] for index in chosen_indices}
    selected = [eligible[index] for index in chosen_indices]
    for candidate in eligible:
        if candidate["task_id"] not in chosen_ids:
            excluded.append({"task_id": candidate["task_id"], "reason": "lower_value_under_constraints"})

    tier = {"correction": 0, "targeted_variant": 0, "diagnostic": 0, "review": 1, "practice": 2, "learn": 3, "timed_practice": 2}
    selected.sort(key=lambda item: (tier.get(item.get("task_type", "practice"), 2), item.get("due_at", "9999"), -item["score_breakdown"]["total"], item["task_id"]))
    cursor = 0
    scheduled: list[dict[str, Any]] = []
    for candidate in selected:
        item = dict(candidate)
        item["start_minute"] = cursor
        cursor += item["estimated_minutes"]
        item["end_minute"] = cursor
        scheduled.append(item)
    subject_minutes: dict[str, int] = {}
    for item in scheduled:
        subject_minutes[item["subject"]] = subject_minutes.get(item["subject"], 0) + item["estimated_minutes"]
    warnings = [
        "Priority scores are transparent heuristics, not calibrated score-gain probabilities.",
        "The scheduler selects among supplied or derived candidates; Codex remains responsible for task quality and live diagnosis.",
    ]
    if cursor < request["available_minutes"] and eligible:
        warnings.append("Some time remains unused because no additional indivisible task satisfied all constraints.")
    return {
        "schema_version": "1.0",
        "model_version": config.get("model_version", SCHEDULER_MODEL_VERSION),
        "phase": config.get("current_phase", "unspecified"),
        "as_of": as_of.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        "available_minutes": request["available_minutes"],
        "scheduled_minutes": cursor,
        "remaining_minutes": request["available_minutes"] - cursor,
        "objective_score": round(sum(item["score_breakdown"]["total"] for item in scheduled), 6),
        "selection_method": "bounded_dynamic_programming",
        "optimality_claim": "none",
        "constraints": {
            "phase_subjects": sorted(phase_subjects),
            "max_subject_share": max_subject_share,
            "fatigue_budget": fatigue_budget,
            "subject_activation": dict(sorted(config.get("subject_activation", {}).items())),
        },
        "subject_minutes": dict(sorted(subject_minutes.items())),
        "selected_tasks": scheduled,
        "excluded_candidates": sorted(excluded, key=lambda item: (item["reason"], item["task_id"])),
        "warnings": warnings,
    }
