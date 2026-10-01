# Mobile request operations

Every request is an envelope with `schema_version`, `request_id`, `created_at`,
`operation`, and `payload`. The payload is operation-specific and must not
contain a transcript.

## Operations

| Operation | Payload | Durable effect |
| --- | --- | --- |
| `record_attempt` | `{ "event": <attempt event> }` | Append one validated attempt |
| `record_diagnosis` | `{ "event": <diagnosis event> }` | Append one diagnosis revision |
| `register_unit` | `{ "unit": <knowledge unit> }` | Add one stable unit to the Vault registry |
| `save_session_result` | `{ "events": [<event>, ...] }` | Atomically append a session batch |
| `request_schedule` | `{ "request": <schedule request> }` | Return an auditable schedule; no event is added |
| `update_source_reference` | `{ "reference": <source reference> }` | Append compact provenance metadata |
| `record_contest_baseline` | `{ "event": <math_contest attempt> }` | Append only when Vault activation allows it |
| `project_change_request` | title, description, acceptance criteria | Record a pending review request; never mutate code |

`record_contest_baseline` is a capability of the public Core. Its activation
date is private Vault policy, so the same Core can be reused by different
learners without importing a personal timetable.

## Receipt semantics

The processor writes `outbox/<request_id>.json` with the same request ID,
request hash, operation, status, and engine version. It is safe to retry a
request after a network failure: the existing receipt is returned if the hash
matches.

Operations execute in a temporary staged Vault. Outputs are published only
after validation and export generation succeed; the same-ID receipt is
published last. Caught publication errors restore earlier file contents before
writing a failed receipt. Run only one writer per Vault: GitHub workflows must
serialize processing, and local processing must not overlap another writer.
This protects against caught errors; it is not a crash-safe, multi-file database
transaction. An abrupt termination requires isolated replay and receipt review.

Invalid JSON or an invalid request envelope produces a file-level CLI failure
and exit code 2, while later independent files are still processed. No receipt
is invented when the request ID or operation is untrustworthy. Existing failed
receipts remain idempotent and require explicit review rather than silent retry.
