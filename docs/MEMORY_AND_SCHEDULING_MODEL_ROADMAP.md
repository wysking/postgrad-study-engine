# Memory and scheduling model roadmap

The engine starts with transparent heuristics. A more complex model is allowed
only when its data requirements, baseline, validation path, and failure behavior
are explicit.

## Upgrade gates

- Keep historical events unchanged.
- Compare every new model with the current deterministic baseline.
- Require replay tests, deterministic outputs, and a rollback path.
- Never describe an uncalibrated score as a probability or guaranteed score gain.
- Let the private Vault decide whether a subject or activity is active.

## Possible future layers

1. Delayed-recall and retention calibration from timestamped evidence.
2. FSRS or another review model after enough delayed-review outcomes exist.
3. Robust scheduling under uncertain time, fatigue, and task duration.
4. Scenario comparison for alternative study routes, using explicit assumptions.
5. Calibration of task value against later independent and timed performance.

Each layer should ship as a versioned Core change with isolated replay fixtures.
