# Schema migrations

Historical learning events are immutable. When a contract must break:

1. add a new schema version and a documented migration;
2. write a fixture proving old data remains readable;
3. rebuild derived state from the original ledger in an isolated workspace;
4. update the Core version and changelog;
5. let each Vault update its lock through a reviewed pull request.

Never rewrite production history in place and never let a failed migration
replace the current Vault state.

## Unreleased receipt and review fixes

Event schema 1.0 remains readable without rewriting the ledger. Rebuilt queues
include hypothesized/unresolved diagnoses, and diagnosis-specific task IDs use
`<kind>:<diagnosis_id>:<unit_id>` so multi-unit diagnoses cannot overwrite each
other. Treat these IDs as derived state: refresh schedules in an isolated
replay before adoption. Equal-timestamp revisions retain append order. Mobile
processing stages writes and rolls back caught publication failures; abrupt
termination and multiple writers still require explicit operational controls.
Publish a reviewed Core release first, then propose a separate lock-only Vault
upgrade. Existing receipts retain their original version and status.
