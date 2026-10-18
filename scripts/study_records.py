"""Append compact study observations independently of the assessment ledger."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from scripts.contracts import (
    ContractError, dump_json_atomic, validate_study_record, validate_study_record_payload,
)


RECORDS_RELATIVE = Path("records/study_records.jsonl")
INDEX_RELATIVE = Path("exports/study_records.json")


class StudyRecordIndexError(ValueError):
    """A derived index is unavailable after the source records were validated."""


def read_records(path: Path) -> tuple[bytes, list[dict[str, Any]]]:
    raw = path.read_bytes() if path.exists() else b""
    try:
        lines = raw.decode("utf-8-sig").splitlines()
    except UnicodeDecodeError as exc:
        raise ContractError("study records must be UTF-8") from exc
    records = []
    seen = set()
    for number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            record = validate_study_record(json.loads(line))
        except (ValueError, TypeError) as exc:
            raise ContractError(f"study records line {number}: {exc}") from exc
        if record["record_id"] in seen:
            raise ContractError(f"duplicate study record: {record['record_id']}")
        seen.add(record["record_id"])
        records.append(record)
    return raw, records


def _write_bytes(path: Path, content: bytes) -> None:
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


def build_index(records: list[dict[str, Any]], revision: str, generated_at: str) -> dict[str, Any]:
    recent = []
    for record in reversed(records[-20:]):
        item = {key: record[key] for key in (
            "record_id", "received_at", "subject_label", "topic", "occurred_at", "occurred_on",
        ) if key in record}
        item.update(summary_excerpt=record["summary"][:300],
                    summary_truncated=len(record["summary"]) > 300,
                    evaluation_status="not_requested")
        recent.append(item)
    return {
        "schema_version": "1.0", "status": "available", "generated_at": generated_at,
        "records_revision": revision, "records_path": RECORDS_RELATIVE.as_posix(),
        "stored_count": len(records), "unassessed_count": len(records), "recent_records": recent,
    }


def save_record(root: Path, request: dict[str, Any], request_hash: str, received_at: str) -> dict[str, Any]:
    payload = validate_study_record_payload(request["payload"])
    record = {
        **payload, "schema_version": "1.0", "record_id": request["request_id"],
        "request_hash": request_hash, "request_created_at": request["created_at"],
        "received_at": received_at,
    }
    if "client" in request:
        record["client"] = request["client"]
    validate_study_record(record)
    path = root / RECORDS_RELATIVE
    raw, records = read_records(path)
    prior = next((item for item in records if item["record_id"] == record["record_id"]), None)
    if prior is not None:
        # Recovery after a missing receipt keeps the first observed receipt time.
        if {k: v for k, v in prior.items() if k != "received_at"} != {
            k: v for k, v in record.items() if k != "received_at"
        }:
            raise ContractError(f"conflicting study record: {record['record_id']}")
        record = prior
        action = "already_present"
    else:
        separator = b"\n" if raw and not raw.endswith((b"\n", b"\r")) else b""
        line = json.dumps(record, ensure_ascii=False, separators=(",", ":")).encode("utf-8") + b"\n"
        raw = raw + separator + line
        _write_bytes(path, raw)
        records.append(record)
        action = "appended"
    revision = hashlib.sha256(raw).hexdigest()
    warnings = []
    try:
        index = build_index(records, revision, received_at)
        index_status = "available"
    except StudyRecordIndexError as exc:
        # Only recognized projection errors degrade. Storage/identity errors fail.
        index = {
            "schema_version": "1.0", "status": "unavailable", "generated_at": received_at,
            "records_revision": revision, "records_path": RECORDS_RELATIVE.as_posix(),
            "stored_count": len(records), "reason": str(exc)[:1000],
        }
        index_status = "unavailable"
        warnings = ["Study record saved; the derived record index is unavailable."]
    dump_json_atomic(root / INDEX_RELATIVE, index)
    return {
        "record_id": record["record_id"], "record_status": "stored", "persistence_action": action,
        "received_at": record["received_at"], "records_path": RECORDS_RELATIVE.as_posix(),
        "records_revision": revision, "evaluation_status": "not_requested",
        "record_index_status": index_status, "record_index_path": INDEX_RELATIVE.as_posix(),
        "warnings": warnings,
    }
