"""Validate the small lock file a private Vault uses to select this Core."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from scripts.contracts import ContractError, load_json


COMMIT_RE = re.compile(r"^[0-9a-fA-F]{40}$")
VERSION_RE = re.compile(r"^v\d+\.\d+\.\d+$")
REPOSITORY_RE = re.compile(r"^[^/\s]+/[^/\s]+$")


def validate_engine_lock(payload: object) -> dict[str, str]:
    if not isinstance(payload, dict):
        raise ContractError("engine lock must be an object")
    allowed = {"repository", "version", "commit", "event_schema"}
    extra = sorted(set(payload) - allowed)
    missing = sorted(allowed - set(payload))
    if extra:
        raise ContractError(f"engine lock has unsupported fields: {', '.join(extra)}")
    if missing:
        raise ContractError(f"engine lock is missing fields: {', '.join(missing)}")
    if not isinstance(payload["repository"], str) or not REPOSITORY_RE.fullmatch(payload["repository"]):
        raise ContractError("engine lock repository must be owner/name")
    if not isinstance(payload["version"], str) or not VERSION_RE.fullmatch(payload["version"]):
        raise ContractError("engine lock version must look like vMAJOR.MINOR.PATCH")
    if not isinstance(payload["commit"], str) or not COMMIT_RE.fullmatch(payload["commit"]):
        raise ContractError("engine lock commit must be a 40-character SHA-1")
    if payload["event_schema"] != "1.0":
        raise ContractError("engine lock event_schema must be '1.0'")
    return {key: str(payload[key]) for key in allowed}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lock", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        payload = validate_engine_lock(load_json(args.lock))
    except (OSError, json.JSONDecodeError, ContractError) as exc:
        print(f"[validate-engine-lock] ERROR: {exc}")
        return 2
    print(json.dumps({"status": "valid", **payload}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
