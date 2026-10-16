# v0.3.1 release review

Status: release candidate, not published. A version in a branch is not a release.

## Scope

PR #1 stages mobile operations, publishes receipts last, rolls back caught
publication errors, preserves unresolved diagnoses, and orders equal-time
revisions by ledger position. PR #2 adds independently verifiable commits for:

1. Positive evidence qualification and unknown overall evidence summaries.
2. Qualified, unit-scoped diagnosis closure and immediate error checks.
3. Explicit same-ID/hash failed-request recovery with prior failure provenance.
4. Due-review, known-prerequisite and overlapping generic-check constraints.
5. Cooperating inbox writer serialization, with Linux/Windows CI coverage.
6. Release-candidate metadata and this review record.

The follow-up offline candidate suite has 103 fictional tests, including 18
normal-mobile-path regressions for target-aware closure, confirmation due
times and known subject identity. The earlier 85-test tree remains the
unmodified PR baseline until these patches are reviewed and adopted.
The separate prior-audit
acceptance harness has 20 requirements. Neither result measures learning gain.
Scoring weights and the score formula are unchanged. No FSRS, BKT or FIRe is
included. Events, requests and receipts retain schema 1.0.

## Required review and release gates

- Review PR #1 at its exact head before merging it.
- Retarget PR #2 to main after #1 is merged; review the final head and base.
- Verify all Linux and Windows jobs, event/example validation and the public
  boundary scan on that final tree. Do not count author testing as independent
  review or infer approval from successful CI.
- Verify `VERSION` and the engine version reported in new receipts/exports.
- Publish the v0.3.1 release/tag for the reviewed exact commit. Update the
  candidate status/date when publication is authorized; check release contents.
- Each Vault separately reviews its cloud writer controls and a lock-only
  upgrade to the published commit. No learning event or existing receipt is
  migrated by the release. Rebuild only in isolated output during review.

## Compatibility and rollback

`heuristic-evidence-0.2` adds optional coverage/counts and can leave overall
unknown despite observations. Consumers must distinguish null from zero.
The repeated-evidence gate is conservative reporting, not validated mastery.
`constrained-priority-0.2` identifies the executed eligibility rules; the old
configuration label is retained in optional `config_model_version`. An old
configuration is usable without changing its weights.

Roll back a Vault by a reviewed lock-only PR to its prior exact release.
Retain append-only events and original receipts, replay to isolated output,
and inspect plans before refreshing production outputs. Never make a failed
operation look successful by editing its receipt. Explicit recovery retains
the old failed receipt and refuses changed identities/content.

## Remaining limits

The follow-up patches address three reproduced release-blocker groups; they
do not establish release readiness. A separate fictional acceptance check
still accepts a purported confirmed draft diagnosis based only on an
ambiguous critical transcription and caller-declared verification. Resolve
that source-admission gate with legacy-read compatibility and positive
controls before declaring the full evidence audit complete. Do not try to
infer truth by keyword matching in learner_verdict. A long-term research
reporter and additional subject contracts are not implemented by these fixes.

The writer guard is advisory and local to one checkout. Cloud runners need a
shared workflow concurrency group and a fresh default-branch checkout; direct
or old-version writers must still be coordinated. Publishing several files is
not a crash-safe database transaction. Hard termination during publication
requires isolated evidence/receipt inspection before replay.

Generic correction/diagnostic checks share one session slot per unit.
Diagnosis-specific tasks remain distinct; their true overlap cannot be inferred
from unit IDs alone. Unknown external units depend on caller qualification.
Priority metrics, intervals, durations and prerequisite thresholds remain
uncalibrated heuristics. Historical delayed-day claims lack verified exposure
timelines, and missing study outcomes remain unestimable. Evaluate scheduling
with subsequent independent attempts rather than internal score changes.
