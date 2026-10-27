# v0.5.1: compatible subject labels for open study records

`save_study_record` accepts `subject` as an input alias for `subject_label`.
Stored records continue to use `subject_label`. Normalization uses a copy, so
the original request and its canonical hash remain unchanged. Equal dual names
are accepted; conflicting or invalid values fail explicitly. CLI receipt
verification understands the normalized representation as well.

There are no new learner fields or assessment requirements. Formal evidence,
scheduling, stored Schema 1.0 and existing histories remain unchanged. Previous
failed receipts are not automatically retried, replaced or marked successful.

Core and optional-model CI gate this release. Existing private Vaults adopt its
exact commit through their reviewed lock-only upgrade process. Recovery of an
old invalid request is a separately reviewed case, preserving original facts and
the original failed receipt. No learner data is included in this release.
