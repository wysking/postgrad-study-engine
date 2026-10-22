# Changelog

## v0.5.0 - 2026-10-22

- Add a single `scripts.study` entry point for safe empty-Vault initialization,
  course registration, observation archival with checked receipts, daily context,
  local HTML reporting and read-only model fitting/evaluation.
- Add an auditable regularized half-life model with prior-only startup and
  chronological evaluation, observed-task skill-risk summaries and prerequisite
  probes that keep hypotheses separate from assessed evidence.
- Add optional pinned py-fsrs integration with explicit observed ratings, an
  opt-in OpenAI Responses teaching adapter and a repository teaching Skill.
- Add independent learner/course/model/rating contracts, a wholly fictional
  nine-unit example, isolation/qualification/leakage tests and optional-model CI.
- Review model numerics: integrate the nonuniform log-half-life grid with cell
  widths, reject duplicate/invalid observations, and version the derived model
  as learning-models-0.2. Verify compact receipts against exact stored records,
  namespace probes across courses and reject malformed API output/archived FSRS units.
- Publish a reproducible known-law synthetic calibration sanity check with
  frozen-fit chronological holdouts, baselines, bins and learner-cluster
  uncertainty. No real-human calibration or learning-effect claim.
- Include the reviewed post-v0.4.0 main-branch evidence qualification, diagnosis
  queue, scheduling eligibility and staged-publication fixes documented below.
- Keep event schema 1.0, historical data/receipts and published tags readable;
  existing private Vaults require separate reviewed adoption. Publish this exact
  authorized version only after Core and optional-model CI pass.

## v0.4.0 - 2026-10-19

- Add `save_study_record`: a compact summary can be archived without assessment
  fields, scheduler configuration, or a learning-state rebuild.
- Keep immutable observations in `records/study_records.jsonl` with stable
  request identity, original request hash, first receipt time and optional
  observed date/time. Preserve existing ledger bytes when appending.
- Publish an independent recent-record index and operation-specific receipt.
  Only recognized derived-index errors degrade; storage and identity failures
  do not become successful records.
- Preserve event Schema 1.0, existing request behavior, scheduling and the
  default full-inbox failure exit code. No automatic assessment or migration.
- Publish this authorized version only after main-branch tests pass; verify
  exact tag/release identity and preserve already published versions. Private
  Vault adoption remains a separate reviewed lock-only upgrade.

## v0.3.1 - 2026-10-16

- Require a qualified, actually tested target for diagnosis completion. Transfer-only and timed-only work cannot be closed by recall, and unmeasured timed work stays open without discarding genuine independent solving evidence.
- Respect future due times for diagnostic, correction and targeted checks as well as reviews; keep explicitly labeled early practice separate from delayed confirmation.
- Exclude scheduler candidates whose subject conflicts with a known unit before applying phase, activation and subject-time constraints.
- Guard new draft-check confirmations when their only critical source is ambiguous; require clear related corroboration while keeping valid 1.0 history readable and unchanged.
- Preserve the existing ledger byte prefix on append, validate duplicate identities and legal diagnosis chains for direct reducer calls, and reject boolean unit durations consistently with the Schema.
- Publish this authorized version only after both operating-system CI jobs pass on the main-branch commit; never replace an existing tag or release.

- Guard each inbox read/stage/publish cycle with a non-blocking operating-system lock; report contention without a sticky failed receipt and release ownership on process exit. Separate runner checkouts still require serialized workflows.
- Enforce review due dates and registered prerequisites for external learning candidates; select at most one generic correction/diagnostic per unit per session without removing unresolved work or changing scoring weights.
- Qualify independent evidence consistently across scoring, success counts and review advancement; keep supported explanations and all failure observations.
- Add positive-evidence counts and coverage; keep overall unknown until target coverage and repeated unassisted evidence support it. Use heuristic-evidence-0.2 without rewriting 1.0 events or changing scheduler weights.
- Align the published independent/assistance rule with runtime validation and reject boolean assistance/delay values.
- Require an active matching parent diagnosis and qualified per-unit performance before closing diagnostic work; explanations cannot substitute for independent solving.
- Keep current errors and unverified results immediately due regardless of a later review recommendation; retain legitimate recall-only closure without solving credit.
- Add an explicit single-request failed-receipt recovery option, preserving the original ID/hash, deduplicating partial historical appends and retaining prior failure provenance. Default processing never silently retries failed receipts.

- Stage each mobile operation before publishing durable outputs and its receipt; restore prior files on caught publication failures.
- Continue processing independent inbox files after an invalid JSON/envelope, while reporting a file failure without inventing a receipt.
- Keep each unresolved diagnosis visible in the review queue without adding it to confirmed error statistics.
- Preserve ledger order for equal-timestamp diagnosis revisions and track targeted completion per knowledge unit.
- Keep event schema 1.0; diagnosis task IDs now include the unit ID. A reviewed release and separate Vault lock upgrade are required before production adoption.

Release status and verification gates: see `docs/RELEASE_REVIEW_0_3_1.md`.

## v0.3.0 - 2026-09-20

- Established the public Core boundary.
- Added mobile request and receipt contracts.
- Added atomic batch event writes and idempotent inbox processing.
- Added Vault-supplied subject activation gates, including the reusable `math_contest` capability.
- Added export refresh for `latest.md` and `latest.json`.
- Added public CI, migration notes, and dual-license notices.
