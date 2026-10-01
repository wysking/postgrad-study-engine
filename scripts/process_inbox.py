"""Process structured mobile requests against a private Vault checkout.

The engine is intentionally storage-agnostic: all personal paths are supplied by
``--vault-root``.  A request is durable only after its operation-specific
validation succeeds and an ``outbox/<request_id>.json`` receipt is written.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.contracts import (
    ContractError,
    append_events_atomic,
    dump_json_atomic,
    load_json,
    load_jsonl,
    parse_datetime,
    validate_knowledge_unit,
    validate_learning_event,
    validate_mobile_request,
    validate_mobile_response,
    validate_source_reference,
)
from scripts.reducer import build_context_capsule, load_units, rebuild_state
from scripts.scheduler import build_schedule


ENGINE_VERSION = "0.3.0"
EVENTS_RELATIVE = Path("events") / "learning_events.jsonl"
UNITS_RELATIVE = Path("state") / "knowledge_units.json"
DERIVED_STATE_RELATIVE = Path("state") / "derived_state.json"
EXPORTS_RELATIVE = Path("exports")
SOURCES_RELATIVE = Path("sources") / "references.jsonl"
CHANGE_REQUESTS_RELATIVE = Path("config") / "personal" / "project_change_requests.jsonl"
DURABLE_OUTPUTS = (
    EVENTS_RELATIVE,
    UNITS_RELATIVE,
    DERIVED_STATE_RELATIVE,
    EXPORTS_RELATIVE / "latest.json",
    EXPORTS_RELATIVE / "latest.md",
    SOURCES_RELATIVE,
    CHANGE_REQUESTS_RELATIVE,
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _request_hash(request: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical(request)).hexdigest()


def _vault_path(vault_root: Path, relative: Path) -> Path:
    return vault_root / relative


def _load_config(vault_root: Path) -> dict[str, Any]:
    candidates = [
        vault_root / "config" / "personal" / "scheduler.json",
        vault_root / "config" / "scheduler.json",
    ]
    for path in candidates:
        if path.exists():
            payload = load_json(path)
            if not isinstance(payload, dict):
                raise ContractError(f"scheduler config must be an object: {path}")
            return payload
    raise ContractError("Vault has no config/personal/scheduler.json or config/scheduler.json")


def _load_registry(vault_root: Path) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    path = _vault_path(vault_root, UNITS_RELATIVE)
    payload = load_json(path) if path.exists() else {"schema_version": "1.0", "units": []}
    if not isinstance(payload, dict) or payload.get("schema_version") != "1.0" or not isinstance(payload.get("units"), list):
        raise ContractError("state/knowledge_units.json must contain schema_version 1.0 and a units array")
    units: dict[str, dict[str, Any]] = {}
    for raw in payload["units"]:
        unit = validate_knowledge_unit(raw)
        if unit["unit_id"] in units:
            raise ContractError(f"duplicate knowledge unit: {unit['unit_id']}")
        units[unit["unit_id"]] = unit
    return payload, units


def _write_jsonl_atomic(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            for record in records:
                handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def _append_jsonl_deduplicated(path: Path, record: dict[str, Any], key: str) -> str:
    existing = []
    if path.exists():
        with path.open("r", encoding="utf-8-sig") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    item = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ContractError(f"{path}:{line_number}: invalid JSON") from exc
                if not isinstance(item, dict):
                    raise ContractError(f"{path}:{line_number}: record must be an object")
                existing.append(item)
    for item in existing:
        if item.get(key) == record.get(key):
            if _canonical(item) == _canonical(record):
                return "already_present"
            raise ContractError(f"conflicting record for {key}={record.get(key)}")
    _write_jsonl_atomic(path, existing + [record])
    return "appended"


def _reject_transcript_fields(value: Any, path: str = "payload") -> None:
    if isinstance(value, dict):
        forbidden = {"transcript", "transcripts", "messages", "conversation", "chat_history", "chat_transcript"}
        found = sorted(forbidden.intersection(value))
        if found:
            raise ContractError(f"{path} contains full-chat fields: {', '.join(found)}")
        for key, child in value.items():
            _reject_transcript_fields(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_transcript_fields(child, f"{path}[{index}]")


def _event_from_payload(payload: dict[str, Any], *, expected_type: str | None = None) -> dict[str, Any]:
    event = payload.get("event")
    if not isinstance(event, dict):
        raise ContractError("payload.event must be an object")
    validate_learning_event(event)
    if expected_type and event["event_type"] != expected_type:
        raise ContractError(f"operation requires event_type={expected_type}")
    return event


def _deduplicate_events(existing: list[dict[str, Any]], incoming: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    by_id = {event["event_id"]: event for event in existing}
    pending: list[dict[str, Any]] = []
    skipped: list[str] = []
    for event in incoming:
        prior = by_id.get(event["event_id"])
        if prior is not None:
            if _canonical(prior) != _canonical(event):
                raise ContractError(f"conflicting event for event_id={event['event_id']}")
            skipped.append(event["event_id"])
            continue
        if any(item["event_id"] == event["event_id"] for item in pending):
            raise ContractError(f"duplicate event_id in request: {event['event_id']}")
        pending.append(event)
        by_id[event["event_id"]] = event
    return pending, skipped


def _refresh_exports(vault_root: Path, *, schedule: dict[str, Any] | None = None) -> dict[str, Any]:
    events_path = _vault_path(vault_root, EVENTS_RELATIVE)
    units_path = _vault_path(vault_root, UNITS_RELATIVE)
    state_path = _vault_path(vault_root, DERIVED_STATE_RELATIVE)
    events = load_jsonl(events_path)
    registry_payload, registry = _load_registry(vault_root)
    state = rebuild_state(events, registry)
    dump_json_atomic(state_path, state)

    exports = _vault_path(vault_root, EXPORTS_RELATIVE)
    exports.mkdir(parents=True, exist_ok=True)
    latest_json = {
        "schema_version": "1.0",
        "generated_at": _utc_now(),
        "engine": {"version": ENGINE_VERSION},
        "state": state,
        "schedule": schedule,
        "registry_count": len(registry_payload["units"]),
    }
    dump_json_atomic(exports / "latest.json", latest_json)
    (exports / "latest.md").write_text(build_context_capsule(state), encoding="utf-8", newline="\n")
    return state


def _activation_blocks(config: dict[str, Any], subject: str, timestamp: str) -> bool:
    raw = config.get("subject_activation", {}).get(subject)
    if raw is None:
        return False
    return parse_datetime(timestamp, "event.timestamp") < parse_datetime(raw, f"config.subject_activation.{subject}")


def _validate_change_request(payload: dict[str, Any]) -> dict[str, Any]:
    required = {"title", "description"}
    missing = sorted(required - set(payload))
    if missing:
        raise ContractError(f"project_change_request missing fields: {', '.join(missing)}")
    allowed = {"title", "description", "requested_files", "acceptance_criteria", "compatibility_notes"}
    extra = sorted(set(payload) - allowed)
    if extra:
        raise ContractError(f"project_change_request has unsupported fields: {', '.join(extra)}")
    for key in ("title", "description", "compatibility_notes"):
        if key in payload and (not isinstance(payload[key], str) or not payload[key].strip()):
            raise ContractError(f"project_change_request.{key} must be a non-empty string")
    for key in ("requested_files", "acceptance_criteria"):
        if key in payload:
            if not isinstance(payload[key], list) or any(not isinstance(item, str) or not item.strip() for item in payload[key]):
                raise ContractError(f"project_change_request.{key} must be an array of non-empty strings")
    return payload


def _response(
    request: dict[str, Any],
    status: str,
    *,
    result: dict[str, Any] | None = None,
    error: dict[str, Any] | None = None,
) -> dict[str, Any]:
    response: dict[str, Any] = {
        "schema_version": "1.0",
        "request_id": request["request_id"],
        "operation": request["operation"],
        "status": status,
        "processed_at": _utc_now(),
        "request_hash": _request_hash(request),
        "engine": {"version": ENGINE_VERSION},
    }
    if result is not None:
        response["result"] = result
    if error is not None:
        response["error"] = error
    validate_mobile_response(response)
    return response


def process_request(vault_root: Path, request: dict[str, Any]) -> dict[str, Any]:
    """Process one validated request and return its receipt."""
    validate_mobile_request(request)
    _reject_transcript_fields(request["payload"])
    payload = request["payload"]
    config = _load_config(vault_root)
    events_path = _vault_path(vault_root, EVENTS_RELATIVE)

    if request["operation"] == "record_attempt":
        events = [_event_from_payload(payload, expected_type="attempt")]
        if _activation_blocks(config, events[0]["subject"], events[0]["timestamp"]):
            raise ContractError(f"subject {events[0]['subject']} is not active at event timestamp")
        existing = load_jsonl(events_path)
        pending, skipped = _deduplicate_events(existing, events)
        if pending:
            append_events_atomic(events_path, pending)
        _refresh_exports(vault_root)
        return _response(request, "succeeded", result={"archived_event_ids": [event["event_id"] for event in pending], "already_present": skipped})

    if request["operation"] == "record_diagnosis":
        event = _event_from_payload(payload, expected_type="diagnosis")
        if _activation_blocks(config, event["subject"], event["timestamp"]):
            raise ContractError(f"subject {event['subject']} is not active at event timestamp")
        existing = load_jsonl(events_path)
        pending, skipped = _deduplicate_events(existing, [event])
        if pending:
            append_events_atomic(events_path, pending)
        _refresh_exports(vault_root)
        return _response(request, "succeeded", result={"archived_event_ids": [event["event_id"] for event in pending], "already_present": skipped})

    if request["operation"] == "save_session_result":
        raw_events = payload.get("events")
        if not isinstance(raw_events, list) or not raw_events:
            raise ContractError("save_session_result.payload.events must be a non-empty array")
        events = []
        for raw_event in raw_events:
            validate_learning_event(raw_event)
            if _activation_blocks(config, raw_event["subject"], raw_event["timestamp"]):
                raise ContractError(f"subject {raw_event['subject']} is not active at event timestamp")
            events.append(raw_event)
        existing = load_jsonl(events_path)
        pending, skipped = _deduplicate_events(existing, events)
        if pending:
            append_events_atomic(events_path, pending)
        _refresh_exports(vault_root)
        return _response(request, "succeeded", result={"archived_event_ids": [event["event_id"] for event in pending], "already_present": skipped})

    if request["operation"] == "register_unit":
        raw_unit = payload.get("unit")
        unit = validate_knowledge_unit(raw_unit)
        registry_payload, units = _load_registry(vault_root)
        prior = units.get(unit["unit_id"])
        if prior is not None:
            if _canonical(prior) != _canonical(unit):
                raise ContractError(f"conflicting knowledge unit: {unit['unit_id']}")
            _refresh_exports(vault_root)
            return _response(request, "succeeded", result={"unit_id": unit["unit_id"], "status": "already_registered"})
        registry_payload["units"].append(unit)
        registry_payload["units"].sort(key=lambda item: item["unit_id"])
        dump_json_atomic(_vault_path(vault_root, UNITS_RELATIVE), registry_payload)
        _refresh_exports(vault_root)
        return _response(request, "succeeded", result={"unit_id": unit["unit_id"], "status": "registered"})

    if request["operation"] == "request_schedule":
        raw_request = payload.get("request")
        if not isinstance(raw_request, dict):
            raise ContractError("request_schedule.payload.request must be an object")
        events = load_jsonl(events_path)
        _, registry = _load_registry(vault_root)
        state = rebuild_state(events, registry)
        schedule = build_schedule(state, raw_request, config)
        _refresh_exports(vault_root, schedule=schedule)
        return _response(request, "succeeded", result={"schedule": schedule})

    if request["operation"] == "update_source_reference":
        reference = validate_source_reference(payload.get("reference"))
        status = _append_jsonl_deduplicated(_vault_path(vault_root, SOURCES_RELATIVE), reference, "reference_id")
        return _response(request, "succeeded", result={"reference_id": reference["reference_id"], "status": status})

    if request["operation"] == "record_contest_baseline":
        event = _event_from_payload(payload, expected_type="attempt")
        if event["subject"] != "math_contest":
            raise ContractError("record_contest_baseline requires subject=math_contest")
        if _activation_blocks(config, event["subject"], event["timestamp"]):
            raise ContractError(f"subject {event['subject']} is not active at event timestamp")
        existing = load_jsonl(events_path)
        pending, skipped = _deduplicate_events(existing, [event])
        if pending:
            append_events_atomic(events_path, pending)
        _refresh_exports(vault_root)
        return _response(request, "succeeded", result={"archived_event_ids": [event["event_id"] for event in pending], "already_present": skipped})

    if request["operation"] == "project_change_request":
        change = _validate_change_request(payload)
        record = {
            "request_id": request["request_id"],
            "created_at": request["created_at"],
            **change,
        }
        status = _append_jsonl_deduplicated(_vault_path(vault_root, CHANGE_REQUESTS_RELATIVE), record, "request_id")
        return _response(request, "pending", result={"status": status, "next_step": "review_and_create_pr"})

    raise ContractError(f"unsupported operation: {request['operation']}")


def _write_receipt(vault_root: Path, request: dict[str, Any], response: dict[str, Any]) -> None:
    outbox = vault_root / "outbox"
    outbox.mkdir(parents=True, exist_ok=True)
    path = outbox / f"{request['request_id']}.json"
    if path.exists():
        existing = load_json(path)
        if not isinstance(existing, dict) or existing.get("request_hash") != response.get("request_hash"):
            raise ContractError(f"outbox receipt already exists for a different request: {request['request_id']}")
        return
    dump_json_atomic(path, response)


def _write_bytes_atomic(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def _publish_outputs(vault_root: Path, staged_root: Path, request_id: str) -> None:
    """Publish a completed operation, with its receipt last; undo caught failures.

    The caller must serialize writers. This is not a crash-safe multi-file
    transaction: an abrupt process termination still requires isolated replay.
    """
    relatives = (*DURABLE_OUTPUTS, Path("outbox") / f"{request_id}.json")
    updates: list[tuple[Path, bytes, bytes | None]] = []
    for relative in relatives:
        staged = staged_root / relative
        if not staged.exists():
            continue
        destination = vault_root / relative
        prior = destination.read_bytes() if destination.exists() else None
        content = staged.read_bytes()
        if content != prior:
            updates.append((destination, content, prior))
    installed: list[tuple[Path, bytes | None]] = []
    try:
        for destination, content, prior in updates:
            _write_bytes_atomic(destination, content)
            installed.append((destination, prior))
    except BaseException:
        for destination, prior in reversed(installed):
            if prior is None:
                destination.unlink()
            else:
                _write_bytes_atomic(destination, prior)
        raise


def process_file(vault_root: Path, request_path: Path) -> dict[str, Any]:
    raw = load_json(request_path)
    request = validate_mobile_request(raw)
    receipt_path = vault_root / "outbox" / f"{request['request_id']}.json"
    if receipt_path.exists():
        existing = load_json(receipt_path)
        if not isinstance(existing, dict) or existing.get("request_hash") != _request_hash(request):
            raise ContractError(f"request_id already has a different receipt: {request['request_id']}")
        validate_mobile_response(existing)
        if existing["request_id"] != request["request_id"] or existing["operation"] != request["operation"]:
            raise ContractError("existing receipt does not match the request ID and operation")
        return existing
    try:
        with tempfile.TemporaryDirectory(prefix="study-request-", ignore_cleanup_errors=True) as temporary:
            staged_root = Path(temporary)
            inputs = (*DURABLE_OUTPUTS, Path("config/personal/scheduler.json"), Path("config/scheduler.json"))
            for relative in inputs:
                source = vault_root / relative
                if source.exists():
                    destination = staged_root / relative
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source, destination)
            response = process_request(staged_root, request)
            _write_receipt(staged_root, request, response)
            _publish_outputs(vault_root, staged_root, request["request_id"])
    except (ContractError, OSError, ValueError) as exc:
        response = _response(request, "failed", error={"code": type(exc).__name__, "message": str(exc)})
        _write_receipt(vault_root, request, response)
    return response


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vault-root", type=Path, required=True)
    parser.add_argument("--request", type=Path, help="Process one request instead of all inbox/*.json files")
    args = parser.parse_args(argv)
    paths = [args.request] if args.request else sorted((args.vault_root / "inbox").glob("*.json"))
    if not paths:
        print(json.dumps({"status": "idle", "processed": 0}, ensure_ascii=False))
        return 0
    responses = []
    for path in paths:
        try:
            responses.append(process_file(args.vault_root, path))
        except (ContractError, OSError, ValueError) as exc:
            # An invalid envelope has no trustworthy ID/operation for a receipt.
            # Report the file failure and continue processing independent files.
            responses.append({
                "status": "failed", "request_file": path.name,
                "error": {"code": type(exc).__name__, "message": str(exc)},
            })
    print(json.dumps({"status": "processed", "responses": responses}, ensure_ascii=False))
    return 2 if any(response["status"] == "failed" for response in responses) else 0


if __name__ == "__main__":
    raise SystemExit(main())
