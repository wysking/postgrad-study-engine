"""Dependency-free contract validation and JSON/JSONL helpers."""

from __future__ import annotations

import json
import math
import os
import re
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable


SUBJECTS = {
    "math",
    "english",
    "materials",
    "politics",
    "physical_chemistry",
    "math_contest",
}
EVENT_TYPES = {"attempt", "diagnosis"}
REQUEST_OPERATIONS = {
    "record_attempt",
    "record_diagnosis",
    "register_unit",
    "save_session_result",
    "request_schedule",
    "update_source_reference",
    "record_contest_baseline",
    "project_change_request",
}
RESPONSE_STATUSES = {"succeeded", "failed", "pending"}
ACTIVITIES = {"learn", "recall", "solve", "review", "timed_practice", "explain", "variant"}
RESULTS = {"correct", "incorrect", "partial", "unanswered"}
ANSWER_MODES = {"independent", "guess", "uncertain", "recalled", "assisted"}
PROCESS_CHECKS = {"clean", "suspicious", "not_available"}
DIAGNOSIS_STATUSES = {"hypothesized", "confirmed", "rejected", "unresolved"}
CONFIRMATION_METHODS = {
    "draft_check",
    "learner_recall",
    "redo",
    "variant",
    "delayed_review",
    "not_confirmed",
}
VARIANT_LEVELS = {"isomorphic", "near_transfer", "boundary", "mixed_transfer"}
EVIDENCE_TARGETS = {"comprehension", "recall", "independent", "transfer", "delayed", "timed"}
UNIT_ID_RE = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z0-9_]+)+$")
EVENT_ID_RE = re.compile(r"^\S+$")
REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
SHA256_RE = re.compile(r"^[a-fA-F0-9]{64}$")


class ContractError(ValueError):
    """Raised when a project contract is violated."""


def _require_mapping(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ContractError(f"{path} must be an object")
    return value


def _require_keys(value: dict[str, Any], keys: Iterable[str], path: str) -> None:
    missing = [key for key in keys if key not in value]
    if missing:
        raise ContractError(f"{path} missing required fields: {', '.join(missing)}")


def _reject_extra(value: dict[str, Any], allowed: set[str], path: str) -> None:
    extra = sorted(set(value) - allowed)
    if extra:
        raise ContractError(f"{path} has unsupported fields: {', '.join(extra)}")


def _require_enum(value: Any, allowed: set[str], path: str) -> str:
    if not isinstance(value, str) or value not in allowed:
        raise ContractError(f"{path} must be one of: {', '.join(sorted(allowed))}")
    return str(value)


def _require_number(value: Any, path: str, minimum: float | None = None, maximum: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise ContractError(f"{path} must be a finite number")
    number = float(value)
    if minimum is not None and number < minimum:
        raise ContractError(f"{path} must be >= {minimum}")
    if maximum is not None and number > maximum:
        raise ContractError(f"{path} must be <= {maximum}")
    return number


def parse_datetime(value: Any, path: str = "timestamp") -> datetime:
    if not isinstance(value, str) or not value:
        raise ContractError(f"{path} must be an ISO-8601 datetime")
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ContractError(f"{path} must be an ISO-8601 datetime") from exc
    if parsed.tzinfo is None:
        raise ContractError(f"{path} must include a timezone")
    return parsed


def _validate_string_list(
    value: Any,
    path: str,
    *,
    pattern: re.Pattern[str] | None = None,
    allow_empty: bool = False,
) -> list[str]:
    if not isinstance(value, list) or (not value and not allow_empty):
        qualifier = "an array" if allow_empty else "a non-empty array"
        raise ContractError(f"{path} must be {qualifier}")
    if any(not isinstance(item, str) or not item for item in value):
        raise ContractError(f"{path} must contain non-empty strings")
    if len(value) != len(set(value)):
        raise ContractError(f"{path} must not contain duplicates")
    if pattern and any(not pattern.fullmatch(item) for item in value):
        raise ContractError(f"{path} contains an invalid identifier")
    return value


def validate_knowledge_unit(unit: Any) -> dict[str, Any]:
    unit = _require_mapping(unit, "knowledge_unit")
    allowed = {
        "schema_version", "unit_id", "subject", "title", "description", "prerequisites",
        "transfer_links", "evidence_targets", "exam_weight", "estimated_minutes", "status", "tags",
    }
    _reject_extra(unit, allowed, "knowledge_unit")
    _require_keys(unit, ("schema_version", "unit_id", "subject", "title"), "knowledge_unit")
    if unit["schema_version"] != "1.0":
        raise ContractError("knowledge_unit.schema_version must be '1.0'")
    if not isinstance(unit["unit_id"], str) or not UNIT_ID_RE.fullmatch(unit["unit_id"]):
        raise ContractError("knowledge_unit.unit_id has invalid format")
    _require_enum(unit["subject"], SUBJECTS, "knowledge_unit.subject")
    if not isinstance(unit["title"], str) or not unit["title"].strip():
        raise ContractError("knowledge_unit.title must be non-empty")
    for key in ("prerequisites", "transfer_links"):
        if key in unit:
            _validate_string_list(unit[key], f"knowledge_unit.{key}", pattern=UNIT_ID_RE, allow_empty=True)
    if "evidence_targets" in unit:
        targets = _validate_string_list(unit["evidence_targets"], "knowledge_unit.evidence_targets")
        for target in targets:
            _require_enum(target, EVIDENCE_TARGETS, "knowledge_unit.evidence_targets[]")
    if "exam_weight" in unit:
        _require_number(unit["exam_weight"], "knowledge_unit.exam_weight", 0, 1)
    if "estimated_minutes" in unit and (isinstance(unit["estimated_minutes"], bool) or not isinstance(unit["estimated_minutes"], int) or unit["estimated_minutes"] < 1):
        raise ContractError("knowledge_unit.estimated_minutes must be an integer >= 1")
    if unit.get("status", "active") not in {"active", "archived"}:
        raise ContractError("knowledge_unit.status must be active or archived")
    for key in ("description",):
        if key in unit and not isinstance(unit[key], str):
            raise ContractError(f"knowledge_unit.{key} must be a string")
    if "tags" in unit:
        _validate_string_list(unit["tags"], "knowledge_unit.tags", allow_empty=True)
    return unit


def validate_diagnosis(diagnosis: Any) -> dict[str, Any]:
    diagnosis = _require_mapping(diagnosis, "diagnosis")
    allowed = {
        "diagnosis_id", "question_id", "status", "generated_by", "confidence",
        "first_divergence", "root_cause", "error_tags", "evidence_refs", "learner_verdict",
        "confirmation_method", "supersedes_event_id", "next_action",
    }
    _reject_extra(diagnosis, allowed, "diagnosis")
    _require_keys(diagnosis, ("diagnosis_id", "question_id", "status", "generated_by"), "diagnosis")
    for key in ("diagnosis_id", "question_id"):
        if not isinstance(diagnosis[key], str) or not diagnosis[key].strip():
            raise ContractError(f"diagnosis.{key} must be non-empty")
    _require_enum(diagnosis["status"], DIAGNOSIS_STATUSES, "diagnosis.status")
    _require_enum(diagnosis["generated_by"], {"codex", "learner", "joint"}, "diagnosis.generated_by")
    if "confidence" in diagnosis:
        _require_number(diagnosis["confidence"], "diagnosis.confidence", 0, 1)
    for key in (
        "first_divergence", "root_cause", "learner_verdict", "supersedes_event_id", "next_action",
    ):
        if key in diagnosis and (not isinstance(diagnosis[key], str) or not diagnosis[key].strip()):
            raise ContractError(f"diagnosis.{key} must be a non-empty string")
    for key in ("error_tags", "evidence_refs"):
        if key in diagnosis:
            _validate_string_list(diagnosis[key], f"diagnosis.{key}")
    if "confirmation_method" in diagnosis:
        _require_enum(diagnosis["confirmation_method"], CONFIRMATION_METHODS, "diagnosis.confirmation_method")
    if diagnosis["status"] == "confirmed":
        if not diagnosis.get("first_divergence") and not diagnosis.get("root_cause"):
            raise ContractError("confirmed diagnosis needs first_divergence or root_cause")
        if not diagnosis.get("learner_verdict"):
            raise ContractError("confirmed diagnosis needs learner_verdict")
        method = diagnosis.get("confirmation_method")
        if method not in CONFIRMATION_METHODS - {"not_confirmed"}:
            raise ContractError("confirmed diagnosis needs a valid confirmation_method")
    return diagnosis


def validate_learning_event(event: Any) -> dict[str, Any]:
    event = _require_mapping(event, "learning_event")
    allowed = {
        "schema_version", "event_id", "timestamp", "event_type", "subject", "unit_ids",
        "activity", "source_ref", "source_hash", "transcription", "transcription_uncertainty",
        "attempt", "diagnosis", "next_action", "recommended_review_at",
    }
    _reject_extra(event, allowed, "learning_event")
    _require_keys(event, ("schema_version", "event_id", "timestamp", "event_type", "subject", "unit_ids"), "learning_event")
    if event["schema_version"] != "1.0":
        raise ContractError("learning_event.schema_version must be '1.0'")
    if not isinstance(event["event_id"], str) or not EVENT_ID_RE.fullmatch(event["event_id"]):
        raise ContractError("learning_event.event_id must be non-empty and contain no whitespace")
    parse_datetime(event["timestamp"], "learning_event.timestamp")
    _require_enum(event["event_type"], EVENT_TYPES, "learning_event.event_type")
    _require_enum(event["subject"], SUBJECTS, "learning_event.subject")
    _validate_string_list(event["unit_ids"], "learning_event.unit_ids", pattern=UNIT_ID_RE)
    if "source_hash" in event and (not isinstance(event["source_hash"], str) or not SHA256_RE.fullmatch(event["source_hash"])):
        raise ContractError("learning_event.source_hash must be a SHA-256 hex digest")
    if "recommended_review_at" in event:
        parse_datetime(event["recommended_review_at"], "learning_event.recommended_review_at")
    for key in ("source_ref", "next_action"):
        if key in event and (not isinstance(event[key], str) or not event[key].strip()):
            raise ContractError(f"learning_event.{key} must be a non-empty string")
    if "transcription" in event and not isinstance(event["transcription"], str):
        raise ContractError("learning_event.transcription must be a string")
    if "transcription_uncertainty" in event:
        _validate_string_list(event["transcription_uncertainty"], "learning_event.transcription_uncertainty", allow_empty=True)
    if event["event_type"] == "attempt":
        if "diagnosis" in event:
            raise ContractError("attempt event cannot contain diagnosis")
        _require_keys(event, ("activity", "attempt"), "learning_event")
        _require_enum(event["activity"], ACTIVITIES, "learning_event.activity")
        validate_attempt(event["attempt"])
    else:
        if "attempt" in event:
            raise ContractError("diagnosis event cannot contain attempt")
        _require_keys(event, ("diagnosis",), "learning_event")
        validate_diagnosis(event["diagnosis"])
    return event


def validate_source_reference(reference: Any) -> dict[str, Any]:
    reference = _require_mapping(reference, "source_reference")
    allowed = {
        "reference_id", "kind", "label", "locator", "edition", "local_path",
        "source_hash", "notes",
    }
    _reject_extra(reference, allowed, "source_reference")
    _require_keys(reference, ("reference_id", "kind", "label"), "source_reference")
    if not isinstance(reference["reference_id"], str) or not EVENT_ID_RE.fullmatch(reference["reference_id"]):
        raise ContractError("source_reference.reference_id must be non-empty and contain no whitespace")
    _require_enum(reference["kind"], {"book", "question", "image", "official_notice", "other"}, "source_reference.kind")
    for key in ("label", "locator", "edition", "local_path", "notes"):
        if key in reference and (not isinstance(reference[key], str) or not reference[key].strip()):
            raise ContractError(f"source_reference.{key} must be a non-empty string")
    if "source_hash" in reference and (not isinstance(reference["source_hash"], str) or not SHA256_RE.fullmatch(reference["source_hash"])):
        raise ContractError("source_reference.source_hash must be a SHA-256 hex digest")
    return reference


def validate_mobile_request(request: Any) -> dict[str, Any]:
    request = _require_mapping(request, "mobile_request")
    allowed = {"schema_version", "request_id", "created_at", "operation", "payload", "client"}
    _reject_extra(request, allowed, "mobile_request")
    _require_keys(request, ("schema_version", "request_id", "created_at", "operation", "payload"), "mobile_request")
    if request["schema_version"] != "1.0":
        raise ContractError("mobile_request.schema_version must be '1.0'")
    if not isinstance(request["request_id"], str) or not REQUEST_ID_RE.fullmatch(request["request_id"]):
        raise ContractError("mobile_request.request_id must be a safe path component up to 128 characters")
    parse_datetime(request["created_at"], "mobile_request.created_at")
    _require_enum(request["operation"], REQUEST_OPERATIONS, "mobile_request.operation")
    _require_mapping(request["payload"], "mobile_request.payload")
    if "client" in request and (not isinstance(request["client"], str) or not request["client"].strip()):
        raise ContractError("mobile_request.client must be a non-empty string")
    return request


def validate_mobile_response(response: Any) -> dict[str, Any]:
    response = _require_mapping(response, "mobile_response")
    allowed = {"schema_version", "request_id", "operation", "status", "processed_at", "result", "error", "request_hash", "engine"}
    _reject_extra(response, allowed, "mobile_response")
    _require_keys(response, ("schema_version", "request_id", "operation", "status", "processed_at"), "mobile_response")
    if response["schema_version"] != "1.0":
        raise ContractError("mobile_response.schema_version must be '1.0'")
    if not isinstance(response["request_id"], str) or not REQUEST_ID_RE.fullmatch(response["request_id"]):
        raise ContractError("mobile_response.request_id must be a safe path component up to 128 characters")
    _require_enum(response["operation"], REQUEST_OPERATIONS, "mobile_response.operation")
    _require_enum(response["status"], RESPONSE_STATUSES, "mobile_response.status")
    parse_datetime(response["processed_at"], "mobile_response.processed_at")
    if "result" in response:
        _require_mapping(response["result"], "mobile_response.result")
    if "error" in response:
        _require_mapping(response["error"], "mobile_response.error")
    if "request_hash" in response and (not isinstance(response["request_hash"], str) or not SHA256_RE.fullmatch(response["request_hash"])):
        raise ContractError("mobile_response.request_hash must be a SHA-256 hex digest")
    if "engine" in response:
        _require_mapping(response["engine"], "mobile_response.engine")
    return response


def validate_attempt(attempt: Any) -> dict[str, Any]:
    attempt = _require_mapping(attempt, "attempt")
    allowed = {
        "question_id", "result", "answer_mode", "process_check", "assistance_level",
        "time_minutes", "confidence_before", "confidence_after", "evidence", "variant_level",
        "parent_diagnosis_id", "delayed_days",
    }
    _reject_extra(attempt, allowed, "attempt")
    _require_keys(attempt, ("question_id", "result", "answer_mode", "process_check", "assistance_level"), "attempt")
    if not isinstance(attempt["question_id"], str) or not attempt["question_id"].strip():
        raise ContractError("attempt.question_id must be non-empty")
    _require_enum(attempt["result"], RESULTS, "attempt.result")
    _require_enum(attempt["answer_mode"], ANSWER_MODES, "attempt.answer_mode")
    _require_enum(attempt["process_check"], PROCESS_CHECKS, "attempt.process_check")
    if isinstance(attempt["assistance_level"], bool) or not isinstance(attempt["assistance_level"], int) or not 0 <= attempt["assistance_level"] <= 5:
        raise ContractError("attempt.assistance_level must be an integer from 0 to 5")
    if "time_minutes" in attempt:
        _require_number(attempt["time_minutes"], "attempt.time_minutes", minimum=0.000001)
    for key in ("confidence_before", "confidence_after"):
        if key in attempt:
            _require_number(attempt[key], f"attempt.{key}", 0, 1)
    if "variant_level" in attempt:
        _require_enum(attempt["variant_level"], VARIANT_LEVELS, "attempt.variant_level")
        if "parent_diagnosis_id" not in attempt:
            raise ContractError("variant attempt needs parent_diagnosis_id")
    if "delayed_days" in attempt and (isinstance(attempt["delayed_days"], bool) or not isinstance(attempt["delayed_days"], int) or attempt["delayed_days"] < 0):
        raise ContractError("attempt.delayed_days must be an integer >= 0")
    for key in ("evidence", "parent_diagnosis_id"):
        if key in attempt and (not isinstance(attempt[key], str) or not attempt[key].strip()):
            raise ContractError(f"attempt.{key} must be a non-empty string")
    if attempt["answer_mode"] == "independent" and attempt["assistance_level"] != 0:
        raise ContractError("independent attempt must have assistance_level 0")
    return attempt


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def dump_json_atomic(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def load_jsonl(path: Path, *, validate: bool = True) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    events: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8-sig") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                event = json.loads(line)
                if validate:
                    validate_learning_event(event)
            except (json.JSONDecodeError, ContractError) as exc:
                raise ContractError(f"{path}:{line_number}: {exc}") from exc
            events.append(event)
    if validate:
        validate_event_sequence(events, validate_items=False)
    return events


def validate_event_sequence(events: list[dict[str, Any]], *, validate_items: bool = True) -> None:
    seen_event_ids: set[str] = set()
    latest_diagnosis: dict[str, dict[str, Any]] = {}
    for index, event in enumerate(events, start=1):
        if validate_items:
            validate_learning_event(event)
        event_id = event["event_id"]
        if event_id in seen_event_ids:
            raise ContractError(f"duplicate event_id: {event_id}")
        seen_event_ids.add(event_id)
        if event["event_type"] != "diagnosis":
            continue
        diagnosis = event["diagnosis"]
        diagnosis_id = diagnosis["diagnosis_id"]
        prior = latest_diagnosis.get(diagnosis_id)
        previous_id = diagnosis.get("supersedes_event_id")
        if prior is None and previous_id:
            raise ContractError(f"event {index}: supersedes_event_id has no prior revision for diagnosis_id")
        if prior is not None:
            if not previous_id:
                raise ContractError(f"event {index}: repeated diagnosis_id requires supersedes_event_id")
            if previous_id != prior["event_id"]:
                raise ContractError(f"event {index}: diagnosis revision must supersede the latest revision")
            if parse_datetime(event["timestamp"]) < parse_datetime(prior["timestamp"]):
                raise ContractError(f"event {index}: diagnosis revision timestamp cannot precede the prior revision")
        latest_diagnosis[diagnosis_id] = event


def append_event_atomic(path: Path, event: dict[str, Any]) -> None:
    append_events_atomic(path, [event])


def _validate_new_diagnosis_source(event: dict[str, Any], prior_events: list[dict[str, Any]]) -> None:
    """Guard new ambiguous draft confirmations without invalidating legacy reads.

    This verifies observable provenance conditions, not the truth of free text.
    A clear corroboration must cover every affected unit on the same question
    or explicitly belong to this diagnostic episode, and cannot be future data.
    """
    if event["event_type"] != "diagnosis":
        return
    diagnosis = event["diagnosis"]
    if diagnosis["status"] != "confirmed" or diagnosis.get("confirmation_method") != "draft_check":
        return
    refs = set(diagnosis.get("evidence_refs", []))
    cited = [item for item in prior_events if item["event_id"] in refs]
    ambiguous = bool(event.get("transcription_uncertainty")) or any(
        item.get("transcription_uncertainty") for item in cited
    )
    if not ambiguous:
        return
    covered: set[str] = set()
    for item in cited:
        if (item["event_type"] != "attempt" or item["subject"] != event["subject"]
                or item.get("transcription_uncertainty")
                or parse_datetime(item["timestamp"]) > parse_datetime(event["timestamp"])):
            continue
        attempt = item["attempt"]
        matching = (attempt["question_id"] == diagnosis["question_id"]
                    or attempt.get("parent_diagnosis_id") == diagnosis["diagnosis_id"])
        if (matching and attempt["process_check"] != "not_available"
                and (attempt.get("evidence", "").strip() or item.get("transcription", "").strip())):
            covered.update(item["unit_ids"])
    if not set(event["unit_ids"]).issubset(covered):
        raise ContractError("ambiguous draft cannot confirm diagnosis without clear, related corroborating evidence; keep it hypothesized or unresolved")


def append_events_atomic(path: Path, events: list[dict[str, Any]]) -> None:
    """Validate and append a batch without exposing a partially written ledger."""
    if not events:
        return
    for event in events:
        validate_learning_event(event)
    existing = load_jsonl(path)
    validate_event_sequence(existing + events, validate_items=False)
    prior = list(existing)
    for event in events:
        _validate_new_diagnosis_source(event, prior)
        prior.append(event)
    prefix = path.read_bytes() if path.exists() else b""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(prefix)
            if prefix and not prefix.endswith((b"\n", b"\r")):
                handle.write(b"\n")
            for event in events:
                handle.write((json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8"))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise
