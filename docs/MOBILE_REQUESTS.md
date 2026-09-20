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
