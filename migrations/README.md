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

## Unreleased evidence qualification

heuristic-evidence-0.2 keeps event schema 1.0 and adds optional unit-level
positive-evidence counts and coverage in rebuilt state. Overall summaries may
now be null even when one dimension has observations. Consumers must keep
unknown distinct from zero. Rebuild from the same ledger, compare outputs, and
refresh schedules before a reviewed release and separate Vault lock upgrade.
The two-success gate is a conservative reporting rule, not a calibrated mastery
criterion. Changed evidence summaries can change derived candidate values;
the separate eligibility change below leaves scoring weights unchanged.

## Unreleased scheduling eligibility

Review tasks with future due dates are excluded with `review_not_due`. Known
unit prerequisites apply equally to external learning/practice candidates;
remediation remains eligible to probe a gap. Generic correction/diagnostic
checks share a per-unit session slot, but diagnosis-specific tasks and the
underlying review queue are preserved. The score formula, weights and input
schema are unchanged. Compare fixed-input plans before adopting these changed
constraints; a different plan is not evidence of improved learning.
Output `model_version` now identifies the executed `constrained-priority-0.2`
implementation. The caller's existing label is retained separately in optional
`config_model_version`; old personal configuration remains readable.

## Explicit failed-request recovery

Old receipts remain unchanged during ordinary replay. The optional single-file
--retry-failed path can replace a reviewed same-ID/hash failed receipt only
after its staged operation succeeds; the new receipt retains the complete prior
failure under result.recovery. An existing event is reused only when its content
matches exactly. Conflicts abort, and receipt publication failures roll back
caught output changes. No production recovery or Vault workflow change is
performed as part of this Core proposal.
