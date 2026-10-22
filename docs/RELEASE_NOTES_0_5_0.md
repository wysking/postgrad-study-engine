# v0.5.0 — teach, observe, fit and check

Learners can now start an empty private Vault, run an authored course, archive
an actual observation, inspect today's evidence gaps and fit their own recall
model through one `python -m scripts.study` entry point. The public Core is
reusable across learners; evidence and fitted parameters stay in separate Vaults.

## Included

- Safe `init`, course registration and receipt-checked `record` / `retry`;
  `today` and a local, network-free HTML report.
- A versioned regularized half-life fit with prior-only startup, auditable
  qualification/exclusions and chronological Brier/log-loss evaluation.
- Observed-task skill risk, prerequisite hypotheses and at most two authored
  diagnostic probes. Suggestions do not become confirmed errors or mastery.
- Optional pinned py-fsrs 6.3.2 integration requiring observed ease grades;
  an offline reference tutor, opt-in OpenAI Responses adapter and repository
  teaching Skill. API responses cannot create learning evidence automatically.
- Nine-unit fictional course and a complete 14-day replay; a reproducible
  24-learner known-law synthetic parameter-recovery/held-out sanity report.
- Reviewed post-v0.4.0 evidence qualification, diagnosis queue, scheduling
  eligibility and staged-write fixes. See [migration notes](../migrations/README.md).

## Review and calibration

Review fixed nonuniform-grid posterior weights, duplicate/invalid model input,
compact-receipt versus actual-record verification, cross-course probe identity,
malformed API output handling and archived-unit FSRS admission. The
[release review](RELEASE_REVIEW_0_5_0.md) records verification and boundaries.

The [synthetic report](CALIBRATION_REPORT_0_5_0.md) scores 480 held-out fictional
predictions: fitted Brier 0.131125 versus fixed-prior 0.203101. Its generator
uses the model's own functional law. **Human calibration, learning gains and
time savings remain unverified.** Nothing switches the global scheduler to a
model-driven default. Paid OpenAI requests and FSRS optimizer dependencies have
not been live-tested; offline transport tests and the real FSRS default adapter
are exercised separately.

## Start and adopt

Use a clean Git checkout of this release with Python 3.12:

```sh
python -m scripts.study demo --vault ../fictional-study-demo
python -m scripts.study today --vault ../fictional-study-demo --as-of 2026-08-15T09:00:00Z
```

Open the demo's `reports/demo.html`. For a real learner, initialize a separate
empty Vault and register actual course units; never import fictional attempts.
See [first-time setup](GETTING_STARTED.md) and [model assumptions](LEARNING_MODELS.md).

Event schema remains 1.0; historical evidence and receipts are not rewritten.
Existing Vaults require separately reviewed identity/course configuration and
an exact-commit lock upgrade. This public release performs no private adoption.
