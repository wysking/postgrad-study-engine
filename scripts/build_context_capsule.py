#!/usr/bin/env python3
"""Create the compact state summary Codex should read at session start."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from scripts.contracts import ContractError, load_json, parse_datetime
from scripts.reducer import build_context_capsule
from scripts.rebuild_state import DEFAULT_OUTPUT


DEFAULT_CAPSULE = Path(__file__).resolve().parents[1] / "state" / "context_capsule.md"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_CAPSULE)
    parser.add_argument("--as-of", type=str)
    parser.add_argument("--max-items", type=int, default=20)
    args = parser.parse_args(argv)
    try:
        state = load_json(args.state)
        as_of = parse_datetime(args.as_of, "--as-of") if args.as_of else None
        capsule = build_context_capsule(state, as_of=as_of, max_items=args.max_items)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(capsule, encoding="utf-8", newline="\n")
        print(json.dumps({"status": "written", "output": str(args.output)}, ensure_ascii=False))
        return 0
    except (OSError, json.JSONDecodeError, ContractError, KeyError) as exc:
        print(f"[context-capsule] ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
