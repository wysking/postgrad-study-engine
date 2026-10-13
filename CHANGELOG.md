# Changelog

## Unreleased

- Qualify independent evidence consistently across scoring, success counts and review advancement; keep supported explanations and all failure observations.
- Add positive-evidence counts and coverage; keep overall unknown until target coverage and repeated unassisted evidence support it. Use heuristic-evidence-0.2 without rewriting 1.0 events or changing scheduler weights.
- Align the published independent/assistance rule with runtime validation and reject boolean assistance/delay values.

- Stage each mobile operation before publishing durable outputs and its receipt; restore prior files on caught publication failures.
- Continue processing independent inbox files after an invalid JSON/envelope, while reporting a file failure without inventing a receipt.
- Keep each unresolved diagnosis visible in the review queue without adding it to confirmed error statistics.
- Preserve ledger order for equal-timestamp diagnosis revisions and track targeted completion per knowledge unit.
- Keep event schema 1.0; diagnosis task IDs now include the unit ID. A reviewed release and separate Vault lock upgrade are required before production adoption.

## v0.3.0 - 2026-09-20

- Established the public Core boundary.
- Added mobile request and receipt contracts.
- Added atomic batch event writes and idempotent inbox processing.
- Added Vault-supplied subject activation gates, including the reusable `math_contest` capability.
- Added export refresh for `latest.md` and `latest.json`.
- Added public CI, migration notes, and dual-license notices.
