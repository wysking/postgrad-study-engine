#!/usr/bin/env python3
"""Rebuild derived learner state from the append-only event ledger."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from scripts.append_event import DEFAULT_EVENTS
from scripts.contracts import ContractError, dump_json_atomic, load_json, load_jsonl
from scripts.reducer import load_units, rebuild_state


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_UNITS = ROOT / "state" / "knowledge_units.json"
DEFAULT_OUTPUT = ROOT / "state" / "derived_state.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", type=Path, default=DEFAULT_EVENTS)
    parser.add_argument("--units", type=Path, default=DEFAULT_UNITS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    try:
        events = load_jsonl(args.events)
        registry = load_units(load_json(args.units)) if args.units.exists() else {}
        state = rebuild_state(events, registry)
        dump_json_atomic(args.output, state)
        print(json.dumps({"status": "rebuilt", "events": len(events), "units": len(state["units"]), "output": str(args.output)}, ensure_ascii=False))
        return 0
    except (OSError, json.JSONDecodeError, ContractError, ValueError) as exc:
        print(f"[rebuild-state] ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
