# Mobile/Vault workflow

The mobile interface may study while the computer is offline. It does not claim
to have changed the private Vault until the Vault's automation processes a
structured request and writes a receipt.

```text
mobile session
  → structured inbox/<request_id>.json
  → Core validates, deduplicates, and applies the operation
  → outbox/<request_id>.json
  → rebuild state and exports/latest.{md,json}
```

## Request rules

- Use `schemas/mobile_request.schema.json` and one of the documented operations
  in `docs/MOBILE_REQUESTS.md`.
- Keep the payload compact. Do not send full chat transcripts or copied source
  works.
- Preserve stable request IDs and event IDs when retrying.
- A repeated identical request is a no-op; a conflicting reuse of an ID fails.
- The mobile client may say “archived” only when the matching receipt has
  `status: "succeeded"`.
- `pending` means that a human review or pull request remains; `failed` means no
  durable archive claim is valid.

## State refresh

Successful evidence operations rebuild the event-derived state and refresh
`exports/latest.md` and `exports/latest.json`. The ledger remains append-only.
The scheduler receives the actual time budget and a reproducible `as_of` value.

## Code and schema changes

Use `project_change_request` for code, schema, or protocol changes. The request
creates a reviewable record; it never edits the Core or bypasses CI. A Vault
engine lock changes only through an upgrade pull request.
