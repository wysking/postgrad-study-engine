# Public Core rules

This repository contains reusable contracts, deterministic support code, teaching protocols, templates, and fictional examples. It is safe to publish only when the checks below remain true.

## Public boundary

- Do not add learner profiles, target schools, personal schedules, real scores, real confidence measurements, real learning events, mobile receipts, credentials, API keys, or local absolute paths.
- Do not commit full paid course files, textbook scans, question-bank dumps, or raw personal photos. Keep only compact provenance records and hashes where needed.
- Examples and tests must be clearly fictional and must not be copied into a private evidence ledger.
- A Vault supplies personal configuration and data at runtime. The Core never assumes a particular learner, school, timetable, or account.

## Evidence and state

- Learning events are append-only and state is rebuildable from the event ledger.
- A model hypothesis is not a confirmed learner error without the evidence gate defined by the diagnosis protocol.
- Heuristic scores are not calibrated probabilities.
- Schema-breaking changes require a versioned migration and compatibility tests; historical events are not rewritten.

## Mobile requests

- Accept only structured requests defined by `schemas/mobile_request.schema.json`.
- Reject full chat transcripts. Every successful durable operation must produce a same-ID outbox receipt.
- Idempotency is mandatory: a repeated request must not append another event.
- Code, schema, and protocol changes are proposed through a change request and reviewed in a pull request.

## Verification

Run the complete test suite before every release:

```powershell
python -m unittest discover -s tests -v
python -m scripts.validate_events
```

The scheduler supports `math_contest` as a reusable capability. Activation dates and phase choices belong to the private Vault configuration, not this repository.
