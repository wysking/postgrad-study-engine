# v0.5.0 release review

Scope: additive public learning-loop implementation in PR #7, plus the reviewed
post-v0.4.0 main-branch reliability changes documented in migrations. The public
Core must remain generic; all examples and calibration inputs are fictional.

## Findings addressed

| Finding | Correction and evidence |
| --- | --- |
| Extra prior-center grid point distorted posterior mass | Log-grid cell-width integration; version `learning-models-0.2`; independent prior-quantile control |
| Direct fitting admitted duplicate or invalid samples | Unique observed IDs, exact binary labels and finite elapsed time checked before fitting |
| An old compact receipt could outlive its missing or altered record | Match one validated stored record against request ID, original hash, payload, client and created time; later valid appends remain compatible |
| Different courses could reuse a probe ID | Namespace by course, preserve source ID, reject duplicate course identity |
| Malformed Responses API output could raise an unhandled type error | Validate output/message/content containers; sanitized contract failures, no evidence writes |
| Archived recall units could enter FSRS | Require active unit, qualified observed result and explicit consistent ease grade |

## Verification

Local review ran **192 tests** with all optional dependencies installed: all
passed, with no skips. The standard-library run also passed (six optional checks
skipped). Empty-ledger validation, clean-checkout demo, Skill validation, JSON
parsing and public path/credential scans passed.

The release is gated on the complete unittest suite and empty-ledger validation
on Linux and Windows. Optional CI installs pinned py-fsrs and independent
JSON Schema validation. Coverage includes learner isolation, unknown startup,
assisted/ambiguous sample exclusion, temporal leakage controls, immutable
requests/retry, exact archived results, course validation, local HTML escaping,
API transport failures and real FSRS replay. The synthetic report is regenerated
and its summary checked in tests; future held-out label changes cannot enter fit.

The repository Skill has been structurally validated and forward-tested in a
disposable fictional Vault: reading an explanation without independent solving
produced only a compact unassessed record, no attempt or mastery declaration.

A clean-checkout CLI demo exercises course registration, 15 fictional events,
model/context construction and HTML output. Public-tree checks cover local
paths, credentials and learner data. The public source registry and event ledger
remain empty. No private Vault lock, personal evidence or workflow is changed.

## Calibration and compatibility judgment

The [published numerical report](CALIBRATION_REPORT_0_5_0.md) is a known-law
synthetic sanity check. It supports implementation correctness under its
assumptions, not human predictive calibration or learning effectiveness. Model
outputs retain `not_validated` / `fitted_uncalibrated` statuses. FSRS optimized
training scores remain labeled in-sample; paid OpenAI transport and optimizer
integration are explicitly outside completed live validation.

Schema 1.0 history stays readable. Derived state can change under the reviewed
evidence/eligibility corrections; compare rebuilt outputs before adoption.
New model reports and namespaced probe IDs are derived outputs, not rewritten
learning events. Existing Vault adoption and rollback use a separate reviewed
exact-lock change. Publication is gated on both Core and optional-model checks,
then verifies the final tag and release metadata against the tested main commit.
