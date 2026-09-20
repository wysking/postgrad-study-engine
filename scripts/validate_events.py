#!/usr/bin/env python3
"""Validate a Postgrad Codex event ledger and report counts."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from scripts.append_event import DEFAULT_EVENTS
from scripts.contracts import ContractError, load_jsonl


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", type=Path, default=DEFAULT_EVENTS)
    args = parser.parse_args(argv)
    try:
        events = load_jsonl(args.events)
        ids = [event["event_id"] for event in events]
        duplicates = sorted(event_id for event_id, count in Counter(ids).items() if count > 1)
        if duplicates:
            raise ContractError(f"duplicate event_id values: {', '.join(duplicates)}")
        print(json.dumps({"status": "valid", "events": len(events), "by_type": dict(Counter(event["event_type"] for event in events))}, ensure_ascii=False))
        return 0
    except (OSError, ContractError) as exc:
        print(f"[validate-events] ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
