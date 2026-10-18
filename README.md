# Postgrad Study Engine

Reusable Core for evidence-based study systems. The repository contains:

- versioned data contracts for knowledge units, learning events, diagnoses, schedules, source references, and mobile requests;
- dependency-free validation, append-only persistence, deterministic state rebuilding, and constrained scheduling;
- a structured `inbox/<request_id>.json` → `outbox/<request_id>.json` integration for a private Vault;
- teaching and error-closure protocols, blank templates, fictional examples, tests, and CI.

Version v0.4.0 adds [compact study records](docs/LIGHTWEIGHT_STUDY_RECORDS.md)
that do not require a complete assessment or modify learning-state estimates.
Release and Vault lock adoption remain separate reviewed steps.
Version v0.3.1 provides the reliability changes described in
[the release review](docs/RELEASE_REVIEW_0_3_1.md). The actual release/tag proves
publication; each Vault's exact engine lock determines its adopted runtime.

The Core contains no learner data. A private Vault supplies its own profile, subjects, events, state, schedule configuration, and engine lock at runtime. The Core is checked out at the exact commit recorded by the Vault; changing that lock is a reviewed upgrade, not an automatic production mutation.

## Local verification

```powershell
python -m unittest discover -s tests -v
python -m scripts.validate_events
```

## Runtime integration

From the Core checkout, process all JSON requests in a Vault inbox:

```powershell
python -m scripts.process_inbox --vault-root C:\path\to\private-vault
```

Only a response with `status: "succeeded"` confirms the corresponding operation.
For `save_study_record`, verify the expected record ID; this does not create an
assessed learning event. For evidence operations, verify the expected event IDs.
`pending` is used for project-change requests that still require review;
`failed` means no durable archive claim may be made.

## Licensing

- Python code: MIT, see `LICENSE`.
- Documentation, protocols, schemas, and templates: CC BY 4.0, see `LICENSE-DOCS-CC-BY-4.0`.
- Third-party textbooks, paid courses, scans, question banks, and other source works are not included or relicensed by this repository.
