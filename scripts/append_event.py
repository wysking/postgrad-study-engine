#!/usr/bin/env python3
"""Validate one JSON learning event and append it without rewriting history."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from scripts.contracts import ContractError, append_event_atomic, load_json


DEFAULT_EVENTS = Path(__file__).resolve().parents[1] / "events" / "learning_events.jsonl"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--event", type=Path, required=True, help="JSON file containing one learning event")
    parser.add_argument("--events", type=Path, default=DEFAULT_EVENTS)
    args = parser.parse_args(argv)
    try:
        event = load_json(args.event)
        append_event_atomic(args.events, event)
        print(json.dumps({"status": "appended", "event_id": event["event_id"], "events": str(args.events)}, ensure_ascii=False))
        return 0
    except (OSError, json.JSONDecodeError, ContractError, KeyError) as exc:
        print(f"[append-event] ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
