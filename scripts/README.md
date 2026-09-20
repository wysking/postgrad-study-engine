# Scripts

Scripts are deterministic support tools, not the primary learning interface.

Implemented utilities:

- `append_event.py`: validate and append one real event;
- `validate_events.py`: validate the full JSONL ledger and unique event IDs;
- `rebuild_state.py`: rebuild mastery evidence, diagnosis state, error recurrence, and review work;
- `build_context_capsule.py`: produce compact Codex session context;
- `schedule_global.py`: select a constrained cross-subject task plan.
- `process_inbox.py`: validate structured Vault requests, apply idempotent operations, write receipts, and refresh exports.

Planned after real evidence exists:

- FSRS integration and personal retention calibration;
- source hashing and registration;
- richer subject coverage and expected-score calibration.

Do not add a web server or user-facing app unless the project scope changes explicitly.
