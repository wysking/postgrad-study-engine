# v0.3.1

Evidence qualification, diagnosis closure and mobile persistence now share stricter observable checks. Assisted or unverifiable success cannot inflate independent-solving evidence; unmeasured timed work and unrelated retrieval cannot close a target that they did not test. Future confirmation tasks wait until due, and known units cannot be scheduled under a different subject label.

Mobile operations stage outputs, publish receipts last and restore prior files on caught failures. Explicit same-request recovery preserves failure provenance. Cooperating local writers use an operating-system lock. Ledger appends preserve existing bytes; direct reducers reject duplicate IDs and invalid revision chains. New ambiguous draft-check confirmations require clear, related corroboration without invalidating historical 1.0 reads.

Compatibility: event/request/receipt Schema 1.0; evidence model heuristic-evidence-0.2; scheduler constrained-priority-0.2. Overall can be null when evidence is insufficient. Existing events and receipts are not migrated; scheduling weights are unchanged. Each Vault adopts an exact release commit in its own lock-only PR.

Validation: 118 fictional unit/integration tests on both CI operating systems, empty demo ledger validation, and separate boundary/behavioral checks. These checks establish software behavior, not measured learning improvement or third-party approval.

Limits: multi-file publication is not crash-safe; distinct runner checkouts need serialized workflows. Source facts still depend on honest observation and caller verification. New subject contracts, automatic longitudinal thinking reports and calibrated mastery models are outside this release.
