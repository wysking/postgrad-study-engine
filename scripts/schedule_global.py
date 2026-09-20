#!/usr/bin/env python3
"""Build a constrained cross-subject study schedule from current state."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from scripts.contracts import ContractError, dump_json_atomic, load_json
from scripts.rebuild_state import DEFAULT_OUTPUT
from scripts.scheduler import build_schedule


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "config" / "scheduler.json"
DEFAULT_SCHEDULE = ROOT / "state" / "current_schedule.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output", type=Path, default=DEFAULT_SCHEDULE)
    args = parser.parse_args(argv)
    try:
        state = load_json(args.state)
        request = load_json(args.request)
        config = load_json(args.config)
        schedule = build_schedule(state, request, config)
        dump_json_atomic(args.output, schedule)
        print(json.dumps({
            "status": "scheduled",
            "tasks": len(schedule["selected_tasks"]),
            "minutes": schedule["scheduled_minutes"],
            "output": str(args.output),
        }, ensure_ascii=False))
        return 0
    except (OSError, json.JSONDecodeError, ContractError, KeyError, ValueError) as exc:
        print(f"[global-scheduler] ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
