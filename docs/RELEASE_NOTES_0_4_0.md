# v0.4.0

Compact study observations can now be saved with only a factual summary through
`save_study_record`. A registered knowledge unit, assessment result, confidence,
assistance level or measured duration is not required. Optional observed dates
remain dates; missing learning times are not inferred from transport timestamps.

A private Vault stores observations separately in `records/study_records.jsonl`
and publishes an independent recent-record index. Stable request identity,
canonical hashes, first receive time and byte-preserving appends support
idempotency and missing-receipt recovery. Records and matching receipts use the
existing single-writer staging and receipt-last publication path. Only a known
derived-index error may degrade; identity, storage and corrupt-record errors
remain failures.

Compatibility: existing formal-event operations and event Schema 1.0 remain
unchanged. Compact observations do not create attempts, change mastery, enter
the scheduler, or become a baseline. Automatic conversion or queued assessment
is outside this release. A consuming Vault must first persist the records path,
then adopt the exact published commit through a separate lock-only upgrade.

Validation: 136 fictional unit/integration tests on both CI operating systems,
including 18 compact-record boundary/recovery checks, plus empty demo-ledger
validation. The version-specific release job verifies final release and tag
identity and never overwrites a published version.

Limits: multi-file publication retains the existing abrupt-termination limit;
independent runner checkouts need serialized workflows. Historic failed
receipts retain the existing nonzero full-inbox exit status. A tool safety
refusal is independent of this feature and must not be repackaged or retried
through the new operation.
