"""Public study entry point: init, course, record, today, fit, evaluate, tutor.

All evidence writes use the existing request processor and matching receipt.
Model/context commands are read-only; reports are separate derived artifacts.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

from scripts.contracts import (ContractError, REQUEST_ID_RE, SUBJECTS, dump_json_atomic,
                               load_json, load_jsonl, parse_datetime, validate_learning_event,
                               validate_mobile_request, validate_study_record_payload)
from scripts.learning_context import (context_for_vault, render_dashboard, render_today,
                                      validate_course, validate_learner_identity)
from scripts.learning_models import evaluate_memory
from scripts.process_inbox import ENGINE_VERSION, _request_hash, process_file
from scripts.reducer import load_units
from scripts.teaching import offline_teach, openai_teach
from scripts.study_records import read_records
from scripts.validate_engine_lock import validate_engine_lock

CORE_ROOT = Path(__file__).resolve().parents[1]


def runtime_commit() -> str:
    try:
        commit = subprocess.check_output(["git", "-C", str(CORE_ROOT), "rev-parse", "HEAD"],
                                         text=True, stderr=subprocess.DEVNULL).strip()
        changed = subprocess.check_output(["git", "-C", str(CORE_ROOT), "status", "--porcelain",
                                           "--untracked-files=normal", "--", "scripts", "schemas", "config",
                                           "VERSION", "examples/courses"],
                                          text=True, stderr=subprocess.DEVNULL)
        if changed.strip():
            raise ContractError("runtime files have uncommitted changes; use a clean reviewed checkout")
        return commit
    except (OSError, subprocess.CalledProcessError):
        raise ContractError("run from a Git checkout so the exact runtime can be verified") from None


def verify_runtime(root: Path) -> None:
    lock = validate_engine_lock(load_json(root / "engine.lock.json"))
    if lock["commit"].lower() != runtime_commit().lower() or lock["version"] != "v" + ENGINE_VERSION:
        raise ContractError("runtime differs from Vault lock; check out its exact commit before continuing")


def init_vault(root: Path, *, demo: bool = False) -> dict:
    if root.exists():
        raise ContractError("destination already exists; initialization never overwrites a Vault")
    commit = runtime_commit()
    lock = validate_engine_lock({"repository": "wysking/postgrad-study-engine", "version": "v" + ENGINE_VERSION,
                                 "commit": commit, "event_schema": "1.0"})
    if not root.parent.is_dir():
        raise ContractError("create the destination's parent directory first")
    with tempfile.TemporaryDirectory(prefix="study-init-", dir=root.parent) as temporary:
        staging = Path(temporary) / "vault"
        (staging / "config/personal").mkdir(parents=True)
        (staging / "inbox").mkdir()
        dump_json_atomic(staging / "engine.lock.json", lock)
        dump_json_atomic(staging / "learner.json", {"schema_version": "1.0", "learner_id": uuid.uuid4().hex,
                                                   "mode": "demo" if demo else "personal"})
        config = load_json(CORE_ROOT / "config/scheduler.json")
        config["current_phase"] = "user_configured"
        dump_json_atomic(staging / "config/personal/scheduler.json", config)
        (staging / ".gitignore").write_text(".env\n.env.*\n*.key\n.study-inbox.lock\n", encoding="utf-8")
        (staging / "START_HERE.md").write_text(
            "# Private learning Vault\n\nKeep this directory private. No learning has been recorded.\n"
            "Use `python -m scripts.study today --vault PATH` from the pinned Core.\n"
            "Review enabled subjects in config/personal/scheduler.json before scheduling.\n"
            "A demo Vault holds fictional evidence only; do not turn it into a personal archive.\n", encoding="utf-8")
        # rename is not used to replace an existing destination. mkdir reserves it.
        root.mkdir()
        try:
            for item in staging.iterdir():
                shutil.move(str(item), root / item.name)
        except BaseException:
            shutil.rmtree(root)
            raise
    return {"status": "initialized", "mode": "demo" if demo else "personal", "learning_events": 0,
            "runtime_commit": commit}


def submit(root: Path, operation: str, payload: dict, request_id: str | None = None) -> dict:
    verify_runtime(root)
    identifier = request_id or "study-" + uuid.uuid4().hex
    if not REQUEST_ID_RE.fullmatch(identifier):
        raise ContractError("request_id is not a safe file component")
    request = {"schema_version": "1.0", "request_id": identifier,
               "created_at": datetime.now(timezone.utc).isoformat(), "client": "study-cli",
               "operation": operation, "payload": payload}
    validate_mobile_request(request)
    if operation == "record_attempt":
        validate_learning_event(payload["event"])
    elif operation == "save_study_record":
        validate_study_record_payload(payload)
    path = root / "inbox" / (identifier + ".json")
    # Preserve immutable requests. Reprocessing uses `retry`, never a new payload.
    with path.open("x", encoding="utf-8") as handle:
        json.dump(request, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    return verified_receipt(root, path, request)


def verified_receipt(root: Path, path: Path, request: dict) -> dict:
    response = process_file(root, path)
    receipt = load_json(root / "outbox" / (request["request_id"] + ".json"))
    if (receipt != response or receipt["request_id"] != request["request_id"]
            or receipt["operation"] != request["operation"] or receipt["request_hash"] != _request_hash(request)):
        raise ContractError("receipt identity, operation or hash mismatch; result remains unverified")
    if receipt["status"] == "failed":
        raise ContractError("request submitted but failed: " + receipt.get("error", {}).get("message", "unknown error"))
    expected = "pending" if request["operation"] == "project_change_request" else "succeeded"
    if receipt["status"] != expected:
        raise ContractError("receipt status does not establish the requested operation")
    if request["operation"] == "record_attempt":
        event = request["payload"]["event"]
        matches = [e for e in load_jsonl(root / "events/learning_events.jsonl") if e["event_id"] == event["event_id"]]
        if matches != [event]:
            raise ContractError("receipt does not match one exact archived event")
    elif request["operation"] == "save_study_record":
        _, records = read_records(root / "records/study_records.jsonl")
        matches = [record for record in records if record["record_id"] == request["request_id"]]
        if (receipt.get("result", {}).get("record_id") != request["request_id"]
                or receipt["result"].get("record_status") != "stored"
                or receipt["result"].get("evaluation_status") != "not_requested" or len(matches) != 1):
            raise ContractError("receipt does not match one stored unassessed record")
        record = matches[0]
        metadata = {"schema_version", "record_id", "request_hash", "request_created_at", "received_at", "client"}
        if ({key: value for key, value in record.items() if key not in metadata} != validate_study_record_payload(request["payload"])
                or record["request_hash"] != receipt["request_hash"]
                or record["request_created_at"] != request["created_at"]
                or record["received_at"] != receipt["result"].get("received_at")
                or record.get("client") != request.get("client")):
            raise ContractError("stored record payload or identity differs from its request")
    return receipt


def install_course(root: Path, course: dict) -> dict:
    verify_runtime(root)
    validate_course(course)
    identity = validate_learner_identity(load_json(root / "learner.json"))
    if course["fictional"] and identity["mode"] != "demo":
        raise ContractError("fictional course belongs only in a new --demo Vault")
    registry_path = root / "state/knowledge_units.json"
    registry = load_units(load_json(registry_path)) if registry_path.exists() else {}
    for unit in course["units"]:
        if unit["unit_id"] in registry and registry[unit["unit_id"]] != unit:
            raise ContractError("course conflicts with an existing unit; use reviewed maintenance")
    course_path = root / "config/courses" / (course["course_id"] + ".json")
    if course_path.exists() and load_json(course_path) != course:
        raise ContractError("course identity already has different content")
    for unit in course["units"]:
        if unit["unit_id"] not in registry:
            submit(root, "register_unit", {"unit": unit})
    dump_json_atomic(course_path, course)
    return {"status": "course_installed", "course_id": course["course_id"],
            "unit_count": len(course["units"]), "learning_events_added": 0}


def record_observation(root: Path, args) -> dict:
    fields = (args.result, args.mode, args.process, args.assistance, args.question, args.unit, args.activity, args.occurred_at)
    if not any(x is not None for x in (*fields, args.delayed_days)):
        return submit(root, "save_study_record", {"summary": args.summary}, args.request_id)
    if any(x is None for x in fields):
        raise ContractError("formal assessment needs unit/activity/question/result/mode/process/assistance/occurred-at; use summary-only for unknowns")
    registry = load_units(load_json(root / "state/knowledge_units.json"))
    if args.unit not in registry:
        raise ContractError("register the actual unit before recording an assessed attempt")
    identifier = args.request_id or "study-" + uuid.uuid4().hex
    event = {"schema_version": "1.0", "event_id": identifier + "-attempt", "timestamp": args.occurred_at,
             "event_type": "attempt", "subject": registry[args.unit]["subject"], "unit_ids": [args.unit],
             "activity": args.activity, "source_ref": "study-cli:observed-response",
             "attempt": {"question_id": args.question, "result": args.result, "answer_mode": args.mode,
                         "process_check": args.process, "assistance_level": args.assistance, "evidence": args.summary}}
    if args.delayed_days is not None:
        event["attempt"]["delayed_days"] = args.delayed_days
    return submit(root, "record_attempt", {"event": event}, identifier)


def run_demo(root: Path) -> dict:
    """Fictional 14-day fixture; never seed a real or pre-existing Vault."""
    init_vault(root, demo=True)
    course = load_json(CORE_ROOT / "examples/courses/limits-and-recall.json")
    install_course(root, course)
    events = load_json(CORE_ROOT / "examples/courses/fictional-14-days.json")["events"]
    for event in events:
        operation = "record_attempt" if event["event_type"] == "attempt" else "record_diagnosis"
        submit(root, operation, {"event": event}, "demo-request-" + event["event_id"])
    context = context_for_vault(root, parse_datetime("2026-08-15T09:00:00Z"))
    report = root / "reports/demo.html"
    report.parent.mkdir(exist_ok=True)
    report.write_text(render_dashboard(context), encoding="utf-8")
    return context


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("init", "course", "record", "retry", "today", "fit", "evaluate", "fsrs", "dashboard", "tutor", "demo"):
        p = commands.add_parser(name)
        p.add_argument("--vault", required=True, type=Path)
        if name == "init":
            p.add_argument("--demo", action="store_true")
        if name == "course":
            p.add_argument("--file", type=Path, required=True)
        if name in {"today", "fit", "evaluate", "fsrs", "dashboard", "tutor"}:
            p.add_argument("--as-of", help="timezone-aware cutoff; defaults to now")
        if name == "fsrs":
            p.add_argument("--ratings", required=True, type=Path)
            p.add_argument("--optimize", action="store_true")
        if name == "today":
            p.add_argument("--minutes", type=int)
            p.add_argument("--json", action="store_true")
        if name == "record":
            p.add_argument("--summary", required=True)
            for flag in ("unit", "activity", "question", "result", "mode", "process", "occurred-at", "request-id"):
                p.add_argument("--" + flag)
            p.add_argument("--assistance", type=int)
            p.add_argument("--delayed-days", type=int)
        if name == "retry":
            p.add_argument("--request-id", required=True)
        if name == "tutor":
            p.add_argument("--question", required=True)
            p.add_argument("--provider", choices=("offline", "openai"), default="offline")
            p.add_argument("--model")
    args = parser.parse_args(argv)
    try:
        if args.command == "init":
            result = init_vault(args.vault, demo=args.demo)
        elif args.command == "demo":
            print(render_today(run_demo(args.vault)), end="")
            return 0
        else:
            verify_runtime(args.vault)
            if args.command == "course":
                result = install_course(args.vault, load_json(args.file))
            elif args.command == "record":
                result = record_observation(args.vault, args)
            elif args.command == "retry":
                if not REQUEST_ID_RE.fullmatch(args.request_id):
                    raise ContractError("unsafe request_id")
                path = args.vault / "inbox" / (args.request_id + ".json")
                result = verified_receipt(args.vault, path, load_json(path))
            else:
                cutoff = parse_datetime(args.as_of) if args.as_of else datetime.now(timezone.utc)
                context = context_for_vault(args.vault, cutoff, getattr(args, "minutes", None))
                if args.command == "today":
                    if args.json:
                        result = context
                    else:
                        print(render_today(context), end="")
                        return 0
                elif args.command == "fit":
                    result = context["models"]
                elif args.command == "evaluate":
                    units_path = args.vault / "state/knowledge_units.json"
                    result = evaluate_memory(load_jsonl(args.vault / "events/learning_events.jsonl"),
                                             load_json(units_path) if units_path.exists() else {"units": []}, cutoff)
                elif args.command == "fsrs":
                    from scripts.fsrs_adapter import fsrs_report
                    path = args.vault / "state/knowledge_units.json"
                    result = fsrs_report(load_jsonl(args.vault / "events/learning_events.jsonl"),
                                         load_json(path) if path.exists() else {"units": []},
                                         load_json(args.ratings), cutoff, context["learner"]["learner_id"],
                                         optimize=args.optimize)
                elif args.command == "dashboard":
                    path = args.vault / "reports/study.html"
                    path.parent.mkdir(exist_ok=True)
                    path.write_text(render_dashboard(context), encoding="utf-8")
                    result = {"status": "rendered", "path": str(path), "scope": "local_private_report"}
                else:
                    text = (openai_teach(context, args.question, args.model) if args.provider == "openai"
                            else offline_teach(context, args.question))
                    print(text)
                    return 0
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        return 0
    except (ContractError, OSError, ValueError, KeyError) as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
