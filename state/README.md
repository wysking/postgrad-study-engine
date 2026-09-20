# Derived State

This directory holds the knowledge-unit registry and compact current estimates derived from learning events.

Implemented layers:

- `knowledge_units.json`: source registry of knowledge units; currently empty.
- `derived_state.json`: generated per-unit heuristic evidence, latest diagnoses, confirmed error patterns, and review queue.
- `context_capsule.md`: generated compact state summary for a study session.
- `current_schedule.json`: generated plan for a specific time budget and phase configuration.
- `../exports/latest.{md,json}`: compact mobile readback generated after a successful Vault operation.

The generated files are created by the corresponding scripts and may not exist before first use. Current phase defaults are in `config/scheduler.json`; the actual available-time budget comes from each scheduling request.

Not implemented: FSRS card state, personal retention calibration, comprehensive subject coverage, and calibrated expected-score risk.

State is a cache of the event history, not a replacement for it. `python -m scripts.rebuild_state` rebuilds it when the evidence model changes; `python -m scripts.build_context_capsule` creates the compact session summary, and `python -m scripts.schedule_global` creates the current constrained plan.

`knowledge_units.json` is source input rather than derived output. Keep stable unit identifiers and validate new entries through the knowledge-unit contract.

Pass an explicit current `--as-of` to `scripts.build_context_capsule` for a mobile handoff. Without it, the script uses the state's generation time (the latest event time, or the epoch for an empty ledger), which is not necessarily today. An uploaded copy is a snapshot and must be refreshed after archiving; see `../docs/MOBILE_DESKTOP_WORKFLOW.md`.
