# Compact study observations

This v0.4.0 capability stores a compact observation without pretending that an
assessment is complete. A summary does not become an attempt, diagnosis,
mastery update, scheduled task or baseline. Existing formal-event operations
and event Schema 1.0 remain unchanged.

## Request

Use the ordinary mobile envelope and `operation: save_study_record`. The payload
requires only `summary`, a nonblank string of at most 12000 characters.
Optional nonblank strings are `subject_label`, `topic`, and `source_ref` (each
also limited to 12000 characters). Optional `occurred_at` needs an ISO datetime
with timezone. `occurred_on` is a real YYYY-MM-DD date. Supply at most one;
missing observed time stays absent.

The stored-record Schema is `schemas/study_record.schema.json`; its `$defs.payload`
describes input fields. Runtime callers use `validate_study_record_payload` and
the isolated full inbox entry point. The request-envelope validator alone is
not sufficient.

Fictional example, never submit this as learner evidence:

```json
{
  "schema_version": "1.0",
  "request_id": "fictional-study-note-001",
  "created_at": "2026-08-10T09:05:00Z",
  "operation": "save_study_record",
  "client": "fictional-example",
  "payload": {
    "summary": "Fictional observation: the result and assistance were not recorded.",
    "subject_label": "Fictional subject",
    "occurred_on": "2026-08-09"
  }
}
```

Unknown result, confidence, assistance, timing or answer mode is not filled with
a default. An optional subject label is organizational text, not registration
or authorization for a scheduler subject. Do not relabel an observation to
enter another subject's assessment or baseline process. Keep summaries compact;
do not include full chats, images or textbook dumps. Preserve the distinction
between observed work, later self-report and model interpretation.

## Storage and receipts

The private Vault supplies `records/study_records.jsonl`; the Core repository
must not contain actual observations. `record_id` equals the first request ID.
The processor adds the canonical `request_hash`, `request_created_at`,
`received_at` and an optional client. Those timestamps describe transport,
not when learning happened. Appends retain the existing file's bytes, including
BOM, newline style and whitespace. Existing record IDs must be unique.

All writes use the normal single-writer, staged, receipt-last publication path.
The first observed receive time is preserved when an identical record exists
without its receipt. Existing matching receipts remain idempotent. Conflicting
request hashes or stored records fail without replacing earlier history.

A matching succeeded receipt includes `record_id`, `record_status: stored`,
`persistence_action`, `received_at`, `records_path`, `records_revision`,
`evaluation_status: not_requested`, `record_index_status` and the index path.
The hash algorithm is the existing canonical mobile-request algorithm, not a
new raw-file-byte identity rule. Preserve the whole original request on retry.

For a remote deployment, records and outbox must be staged in the same Git
commit. The client verifies that remote receipt's ID, operation, available
hash and expected record ID. It does not need to scan every historic record
for each ordinary save. A local test response alone is not remote success.

## Independent index and failure boundary

`exports/study_records.json` reports the source `records_revision`, total
stored/unassessed counts, and the latest 20 observations in append order.
`summary_excerpt` is explicitly a 300-character preview; the source summary
is never truncated. There is no queued assessment or automatic text analysis.

Only `StudyRecordIndexError` is a recognized derived-index degradation: the
source record is retained and a fresh `status: unavailable` index replaces the
old view. The receipt marks the index unavailable and includes a warning.
Storage errors, corrupt source records and identity conflicts are not degraded.
Unexpected implementation bugs are not swallowed. As with existing inbox
operations, abrupt termination is not a crash-safe multi-file transaction;
recovery requires inspection of the same request and remote outputs.

Compact saves do not read the scheduler configuration, registry or assessment
ledger, and do not rewrite existing learning exports. A corrupt assessment
input may prevent assessments while a separate valid observation is saved.
This does not excuse corruption of the record store itself.

The inbox scanner still returns exit 2 for any failed response, including a
historic failure. Check each request's receipt. Do not make all jobs green by
hiding failed requests.

## Adoption, rollback and later assessment

First review and publish a supporting Core, then review the Vault's lock and
workflow persistence changes, then enable its phone template. The workflow
must persist `records` as well as `outbox` and `exports`; the new directory
may be absent before its first record. An unreleased branch is not deployment.
The current release workflow does not automatically publish a new version.

Disable the client entry point or pause new processing when rolling back.
Keep a runtime that recognizes existing new-format requests and receipts;
an older Core cannot simply scan those requests. Never delete records or
receipts to make rollback appear compatible.

Later assessed events need actual complete evidence, explicit provenance to
the original record, stable event IDs and deduplication. This first stage does
not implement conversion or reassessment. Genuine later work is a new
observation; later clarification does not rewrite original work.

A prior tool safety refusal remains stopped. A rejected or failed request is
not automatically repackaged into this operation, assigned a new ID or sent
through a different tool.
