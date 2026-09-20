"""Rebuild current learner state from append-only learning events."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from scripts.contracts import parse_datetime, validate_knowledge_unit


MODEL_VERSION = "heuristic-evidence-0.1"
DIMENSIONS = ("comprehension", "recall", "independent", "transfer", "delayed", "timed")


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def load_units(payload: Any) -> dict[str, dict[str, Any]]:
    if payload is None:
        return {}
    if isinstance(payload, dict) and "units" in payload:
        items = payload["units"]
    else:
        items = payload
    if not isinstance(items, list):
        raise ValueError("knowledge-unit registry must be an array or an object with a units array")
    result: dict[str, dict[str, Any]] = {}
    for item in items:
        validate_knowledge_unit(item)
        unit_id = item["unit_id"]
        if unit_id in result:
            raise ValueError(f"duplicate unit_id: {unit_id}")
        result[unit_id] = item
    return result


def _new_unit_state(unit_id: str, subject: str, registry: dict[str, dict[str, Any]]) -> dict[str, Any]:
    spec = registry.get(unit_id, {})
    return {
        "unit_id": unit_id,
        "subject": subject,
        "title": spec.get("title", unit_id),
        "exam_weight": float(spec.get("exam_weight", 0.5)),
        "estimated_minutes": int(spec.get("estimated_minutes", 20)),
        "prerequisites": list(spec.get("prerequisites", [])),
        "evidence_targets": list(spec.get("evidence_targets", DIMENSIONS)),
        "mastery": {},
        "evidence_counts": {dimension: 0 for dimension in DIMENSIONS},
        "attempts": {"total": 0, "correct": 0, "partial": 0, "incorrect": 0, "unanswered": 0},
        "clean_independent_correct": 0,
        "flagged_correct": 0,
        "assisted_attempts": 0,
        "confidence": {"samples": 0, "absolute_error_sum": 0.0, "overconfident_errors": 0},
        "time_minutes": 0.0,
        "last_event_at": None,
        "last_event_id": None,
    }


def _evidence_dimensions(event: dict[str, Any]) -> list[str]:
    activity = event["activity"]
    attempt = event["attempt"]
    dimensions: list[str] = []
    if activity in {"learn", "explain"}:
        dimensions.append("comprehension")
    if activity in {"recall", "review"}:
        dimensions.append("recall")
    if activity in {"solve", "timed_practice"}:
        dimensions.append("independent")
    if activity == "variant":
        dimensions.append("transfer")
    if activity == "timed_practice":
        dimensions.append("timed")
    if attempt.get("delayed_days", 0) > 0:
        dimensions.append("delayed")
    return list(dict.fromkeys(dimensions or ["comprehension"]))


def _update_mastery(unit: dict[str, Any], event: dict[str, Any]) -> None:
    attempt = event["attempt"]
    result = attempt["result"]
    mode = attempt["answer_mode"]
    assistance = attempt["assistance_level"]
    suspicious = attempt["process_check"] == "suspicious"
    dimensions = _evidence_dimensions(event)
    positive = result == "correct"
    alpha = {"correct": 0.22, "partial": 0.08, "incorrect": 0.18, "unanswered": 0.12}[result]
    if positive:
        if mode == "guess":
            alpha = 0.0
        elif mode == "uncertain":
            alpha *= 0.5
        elif mode in {"recalled", "assisted"}:
            alpha *= 0.7
        alpha *= max(0.25, 1.0 - 0.15 * assistance)
        if suspicious:
            alpha *= 0.5

    for dimension in dimensions:
        old = float(unit["mastery"].get(dimension, 0.5))
        if positive:
            new = old + alpha * (1.0 - old)
        else:
            new = old * (1.0 - alpha)
        unit["mastery"][dimension] = round(max(0.0, min(1.0, new)), 4)
        unit["evidence_counts"][dimension] += 1

    targets = [target for target in unit["evidence_targets"] if target in unit["mastery"]]
    if targets:
        unit["mastery_overall"] = round(sum(unit["mastery"][key] for key in targets) / len(targets), 4)
    else:
        unit["mastery_overall"] = None


def _review_time(event: dict[str, Any]) -> datetime:
    if event.get("recommended_review_at"):
        return parse_datetime(event["recommended_review_at"], "recommended_review_at")
    attempt = event["attempt"]
    timestamp = parse_datetime(event["timestamp"])
    if attempt["result"] != "correct":
        return timestamp
    if attempt["answer_mode"] in {"guess", "uncertain"} or attempt["process_check"] == "suspicious":
        return timestamp
    if attempt["assistance_level"] > 0:
        return timestamp + timedelta(days=1)
    if attempt.get("variant_level") == "isomorphic":
        return timestamp + timedelta(days=3)
    if attempt.get("variant_level") in {"near_transfer", "boundary"}:
        return timestamp + timedelta(days=7)
    if attempt.get("variant_level") == "mixed_transfer":
        return timestamp + timedelta(days=14)
    if attempt.get("delayed_days", 0) > 0:
        return timestamp + timedelta(days=max(7, attempt["delayed_days"] * 2))
    if event["activity"] == "timed_practice":
        return timestamp + timedelta(days=14)
    return timestamp + timedelta(days=3)


def _queue_task(
    queue: dict[str, dict[str, Any]],
    unit: dict[str, Any],
    event: dict[str, Any],
    kind: str,
    reason: str,
    due_at: datetime,
    *,
    diagnosis_id: str | None = None,
    error_tags: list[str] | None = None,
) -> None:
    suffix = diagnosis_id or unit["unit_id"]
    task_id = f"{kind}:{suffix}"
    queue[task_id] = {
        "task_id": task_id,
        "task_type": kind,
        "subject": unit["subject"],
        "unit_id": unit["unit_id"],
        "activity": "variant" if kind == "targeted_variant" else ("solve" if kind in {"diagnostic", "correction"} else "review"),
        "due_at": _iso(due_at),
        "estimated_minutes": unit["estimated_minutes"],
        "reason": reason,
        "source_event_id": event["event_id"],
        "diagnosis_id": diagnosis_id,
        "error_tags": error_tags or [],
    }


def _handle_attempt_queue(queue: dict[str, dict[str, Any]], unit: dict[str, Any], event: dict[str, Any]) -> None:
    attempt = event["attempt"]
    unit_id = unit["unit_id"]
    if attempt["result"] == "correct" and attempt["answer_mode"] == "independent" and attempt["process_check"] == "clean":
        for key in (f"diagnostic:{unit_id}", f"correction:{unit_id}"):
            queue.pop(key, None)
        if attempt.get("parent_diagnosis_id"):
            queue.pop(f"targeted_variant:{attempt['parent_diagnosis_id']}", None)
        _queue_task(queue, unit, event, "review", "delayed confirmation after clean independent success", _review_time(event))
        return
    if attempt["result"] != "correct":
        _queue_task(queue, unit, event, "correction", "incorrect or incomplete attempt needs diagnosis and correction", _review_time(event))
        return
    _queue_task(queue, unit, event, "diagnostic", "correct result was guessed, uncertain, assisted, or process-suspicious", _review_time(event))


def rebuild_state(events: list[dict[str, Any]], registry: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    registry = registry or {}
    ordered = sorted(events, key=lambda item: (parse_datetime(item["timestamp"]), item["event_id"]))
    units: dict[str, dict[str, Any]] = {}
    diagnoses: dict[str, dict[str, Any]] = {}
    queue: dict[str, dict[str, Any]] = {}
    completed_variants: dict[str, datetime] = {}
    warnings: list[str] = []

    for unit_id, spec in sorted(registry.items()):
        if spec.get("status", "active") == "active":
            units[unit_id] = _new_unit_state(unit_id, spec["subject"], registry)

    for event in ordered:
        for unit_id in event["unit_ids"]:
            if unit_id not in units:
                units[unit_id] = _new_unit_state(unit_id, event["subject"], registry)
            elif units[unit_id]["subject"] != event["subject"]:
                raise ValueError(f"unit {unit_id} appears under multiple subjects")
        if event["event_type"] == "attempt":
            attempt = event["attempt"]
            if (
                attempt.get("parent_diagnosis_id")
                and attempt["result"] == "correct"
                and attempt["answer_mode"] == "independent"
                and attempt["process_check"] == "clean"
                and attempt["assistance_level"] == 0
            ):
                diagnosis_id = attempt["parent_diagnosis_id"]
                completed_variants[diagnosis_id] = max(
                    completed_variants.get(diagnosis_id, datetime.min.replace(tzinfo=timezone.utc)),
                    parse_datetime(event["timestamp"]),
                )
            for unit_id in event["unit_ids"]:
                unit = units[unit_id]
                unit["attempts"]["total"] += 1
                unit["attempts"][attempt["result"]] += 1
                if attempt["result"] == "correct" and attempt["answer_mode"] == "independent" and attempt["process_check"] == "clean" and attempt["assistance_level"] == 0:
                    unit["clean_independent_correct"] += 1
                elif attempt["result"] == "correct":
                    unit["flagged_correct"] += 1
                if attempt["assistance_level"] > 0:
                    unit["assisted_attempts"] += 1
                if "time_minutes" in attempt:
                    unit["time_minutes"] = round(unit["time_minutes"] + float(attempt["time_minutes"]), 2)
                if "confidence_before" in attempt and attempt["result"] in {"correct", "incorrect"}:
                    target = 1.0 if attempt["result"] == "correct" else 0.0
                    confidence = float(attempt["confidence_before"])
                    unit["confidence"]["samples"] += 1
                    unit["confidence"]["absolute_error_sum"] = round(unit["confidence"]["absolute_error_sum"] + abs(confidence - target), 4)
                    if target == 0.0 and confidence >= 0.8:
                        unit["confidence"]["overconfident_errors"] += 1
                unit["last_event_at"] = event["timestamp"]
                unit["last_event_id"] = event["event_id"]
                _update_mastery(unit, event)
                _handle_attempt_queue(queue, unit, event)
        else:
            diagnosis = dict(event["diagnosis"])
            diagnosis["event_id"] = event["event_id"]
            diagnosis["timestamp"] = event["timestamp"]
            diagnosis["subject"] = event["subject"]
            diagnosis["unit_ids"] = list(event["unit_ids"])
            diagnoses[diagnosis["diagnosis_id"]] = diagnosis

    error_patterns: dict[str, dict[str, Any]] = defaultdict(lambda: {"count": 0, "diagnosis_ids": [], "unit_ids": [], "subjects": []})
    for diagnosis_id, diagnosis in sorted(diagnoses.items()):
        task_key = f"targeted_variant:{diagnosis_id}"
        if diagnosis["status"] != "confirmed":
            queue.pop(task_key, None)
            continue
        tags = diagnosis.get("error_tags") or ["unclassified"]
        for tag in tags:
            pattern = error_patterns[tag]
            pattern["count"] += 1
            pattern["diagnosis_ids"].append(diagnosis_id)
            pattern["unit_ids"] = sorted(set(pattern["unit_ids"]) | set(diagnosis["unit_ids"]))
            pattern["subjects"] = sorted(set(pattern["subjects"]) | {diagnosis["subject"]})
        for unit_id in diagnosis["unit_ids"]:
            unit = units[unit_id]
            event_stub = {"event_id": diagnosis["event_id"]}
            if completed_variants.get(diagnosis_id, datetime.min.replace(tzinfo=timezone.utc)) >= parse_datetime(diagnosis["timestamp"]):
                continue
            _queue_task(
                queue,
                unit,
                event_stub,
                "targeted_variant",
                diagnosis.get("next_action", "verify confirmed diagnosis with a targeted variant"),
                parse_datetime(diagnosis["timestamp"]),
                diagnosis_id=diagnosis_id,
                error_tags=tags,
            )

    for unit in units.values():
        samples = unit["confidence"]["samples"]
        unit["confidence"]["mean_absolute_error"] = round(unit["confidence"]["absolute_error_sum"] / samples, 4) if samples else None
        del unit["confidence"]["absolute_error_sum"]

    generated = parse_datetime(ordered[-1]["timestamp"]) if ordered else datetime(1970, 1, 1, tzinfo=timezone.utc)
    return {
        "schema_version": "1.0",
        "model_version": MODEL_VERSION,
        "generated_at": _iso(generated),
        "event_count": len(ordered),
        "units": dict(sorted(units.items())),
        "diagnoses": dict(sorted(diagnoses.items())),
        "error_patterns": dict(sorted(error_patterns.items())),
        "review_queue": sorted(queue.values(), key=lambda item: (item["due_at"], item["subject"], item["task_id"])),
        "warnings": warnings + ["Mastery values are heuristic evidence summaries, not calibrated probabilities."],
    }


def build_context_capsule(state: dict[str, Any], *, as_of: datetime | None = None, max_items: int = 20) -> str:
    as_of = as_of or parse_datetime(state["generated_at"], "state.generated_at")
    lines = [
        "# Postgrad Codex Context Capsule",
        "",
        f"- Model: `{state['model_version']}`",
        f"- Events: {state['event_count']}",
        f"- As of: {_iso(as_of)}",
        "",
        "## Due Work",
    ]
    due = [item for item in state["review_queue"] if parse_datetime(item["due_at"]) <= as_of]
    if due:
        for item in due[:max_items]:
            lines.append(f"- `{item['task_id']}` [{item['subject']}] {item['reason']} ({item['estimated_minutes']} min)")
    else:
        lines.append("- None")
    lines.extend(["", "## Confirmed Error Patterns"])
    if state["error_patterns"]:
        for tag, item in sorted(state["error_patterns"].items(), key=lambda pair: (-pair[1]["count"], pair[0]))[:max_items]:
            lines.append(f"- `{tag}`: {item['count']} confirmed; units: {', '.join(item['unit_ids'])}")
    else:
        lines.append("- None")
    lines.extend(["", "## Unit Evidence"])
    ranked = sorted(
        state["units"].values(),
        key=lambda item: (item.get("mastery_overall") is not None, -(1.0 - (item.get("mastery_overall") or 0.0)), item["unit_id"]),
    )
    if ranked:
        for unit in ranked[:max_items]:
            score = "unknown" if unit.get("mastery_overall") is None else f"{unit['mastery_overall']:.2f}"
            lines.append(
                f"- `{unit['unit_id']}` [{unit['subject']}]: mastery={score}, attempts={unit['attempts']['total']}, "
                f"clean_correct={unit['clean_independent_correct']}, flagged_correct={unit['flagged_correct']}"
            )
    else:
        lines.append("- None")
    lines.extend(["", "> Only confirmed diagnoses are durable error evidence. Heuristic mastery is not a mastery declaration.", ""])
    return "\n".join(lines)
