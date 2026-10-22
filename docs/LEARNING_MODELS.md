# Experimental learning loop · 自适应学习闭环

This is an **unreleased implementation under review**, not a hosted service or
a claim of improved learning. The existing formal event schema, evidence rules,
ledger and global scheduler remain unchanged. Each learner uses a private Vault.

## A complete fictional demo

From this proposed Git checkout, using Python 3.12:

```sh
python -m scripts.study demo --vault ../fictional-study-demo
python -m scripts.study today --vault ../fictional-study-demo --as-of 2026-08-15T09:00:00Z
python -m scripts.study fit --vault ../fictional-study-demo --as-of 2026-08-15T09:00:00Z
python -m scripts.study evaluate --vault ../fictional-study-demo --as-of 2026-08-15T09:00:00Z
python -m scripts.study dashboard --vault ../fictional-study-demo --as-of 2026-08-15T09:00:00Z
```

Open `reports/study.html` inside that demo. The static HTML makes no network
requests. The authored fixture spans 14 elapsed days, nine units, fourteen
attempts and one diagnosis. Independent success, day-three failure, assisted
correction, independent variant and a later check remain distinct. Recall
examples actually fit a model and generate chronological evaluation results.
This demonstrates software behavior, not scientific validity. Initialization
refuses an existing directory. The default public registry stays empty.
Never copy fictional evidence into a real archive.

## A new real learner

```sh
python -m scripts.study init --vault ../my-private-vault
python -m scripts.study today --vault ../my-private-vault
python -m scripts.study record --vault ../my-private-vault --summary "Read an explanation; no independent answer was observed."
```

Initialization creates an empty directory with a random stable learner identity
and a lock to the **actual checkout**, not an assumed release. It does not
create GitHub repositories or install remote automation. Keep the Vault private.
Review its enabled subjects and activation policy before formal scheduling.
The CLI compares the checkout SHA and engine version with the lock before
processing; it does not fetch or upgrade code. Use a clean reviewed checkout.
Existing Vaults lacking `learner.json` require separately reviewed adoption;
do not initialize over them or infer an identity during reads.

Install an authored real course with `study course --vault ... --file ...`.
It registers units through matching receipts without adding attempts. Cycles,
missing prerequisites, conflicting definitions and fictional courses in personal
Vaults are rejected. Sample courses cover a limited scope, not a full syllabus.

For an actual assessed attempt, `record` additionally requires observed `--unit`,
`--activity`, `--question`, `--result`, `--mode`, `--process`, `--assistance` and
timezone-aware `--occurred-at`. Add `--delayed-days` only when genuinely measured.
If assessment fields are unknown, use summary-only archival. Do not copy sample
answers or timings. `retry --request-id ID` preserves the unchanged request; it
cannot repair a failed payload or bypass a refusal. The CLI checks its local
receipt, hash and exact archived attempt, not remote GitHub persistence.

`today --minutes N` invokes the original scheduler. Without an actual budget,
it returns suggestions only. Probe suggestions are separate from the formal
plan, not extra scheduled work or completed delayed checks. Ranking uses
auditable heuristics, not claimed expected information gain. Evidence gaps and
observed failures are different reasons to check a prerequisite. Inactive
subjects and pending future confirmations are excluded.

## Model contracts and assumptions

`fit` returns `learning_model.schema.json`: model ID/version, learner ID, cutoff,
input hash, policy, sample audit and estimates. Reports are disposable derived
data, never assessed events. No cross-learner cache or private-data pooling is
used. Future events do not change earlier reports. The registry is a supplied
snapshot, not a reconstruction of historical curriculum changes; preserve it
when reproducing a report.

The standard-library recall baseline uses `R(t,H)=exp(-ln(2)*t/H)`. Bounded
log-half-life grid MAP fitting uses a log-normal prior centered at three days,
log standard deviation `ln(2)`, and bounds 0.125–365 days. These are versioned
**modeling assumptions**, not validated population or learner parameters. Sparse
units shrink to that fixed prior. The 90% interval is conditional on the model,
prior and discrete grid, not calibrated real-world coverage. The grid is uniform
in log half-life with the prior center additionally included; weights approximate
inference numerically. A parameter at a bound is reported explicitly.

Only single-unit atomic recall/review qualifies: registered recall target, no
independent/transfer/timed targets, clean process, zero assistance, known
independent/recalled mode, and correct/incorrect result. A sample needs a prior
qualified correct retrieval, explicit positive `delayed_days`, at least one
actual elapsed day and timestamp agreement within one day. Intervening assessed
activity breaks the anchor. A failure needs a new qualified success before a
new retention interval. Unlogged study is unknown. Multi-unit tasks, missing
delays and uncertain conditions become audited exclusions. Zero samples still
run as `prior_only`; current retention is null without a known anchor.

Skill risk is separate: Beta(1,1)-smoothed failure on observed single-unit,
independent clean solving tasks. It describes that selected task mix, not
general ability, causal weakness or calibrated exam correctness. Error-tag
probabilities stay null because all relevant error opportunities are not
observed. Rejected/unresolved/confirmed diagnoses remain different, and model
suggestions cannot confirm one or increase assessed mastery.

`evaluate` predicts each timestamp group from strictly earlier eligible results,
then updates. It compares fitted half-life, fixed half-life and constant 0.5
using Brier score, log loss and descriptive calibration bins. Empty results
have null metrics. Small samples and fictional data do not establish calibration.
Historical replay cannot show that a different schedule would improve retention
or save time. The old scheduler emits priorities, not comparable recall
probabilities; its scores are not passed into Brier calculations.

## Optional FSRS

```sh
python -m pip install fsrs==6.3.2
python -m scripts.study fsrs --vault ../my-private-vault --ratings private-ratings.json --as-of 2026-08-15T09:00:00Z
```

Input follows `fsrs_ratings.schema.json`: matching learner ID and explicitly
observed ratings linked to qualified events, 1=Again, 2=Hard, 3=Good, 4=Easy.
The complete rated item's intervening history is required. Correctness alone
does not identify an ease grade; the adapter refuses to invent one. It uses UTC
and disables random fuzzing. Suggested dates do not change the global scheduler.
Default-parameter replay is chronological. `--optimize` additionally requires
`fsrs[optimizer]==6.3.2`; its fitted replay scores are labeled **in-sample, not
validation**. Library defaults are priors, not parameters fitted to this learner.

The baseline and default CLI require only the standard library. The optional
adapter is exercised against real py-fsrs. Optimizer dependencies and paid
OpenAI calls are separate checks, never silently claimed as tested.
See [Py-FSRS](https://github.com/open-spaced-repetition/py-fsrs) and the
[chronological SRS benchmark](https://github.com/open-spaced-repetition/srs-benchmark).

## Teaching and Skill

```sh
python -m scripts.study tutor --vault ../my-private-vault --question "Help me reconstruct this step"
python -m scripts.study tutor --vault ../my-private-vault --provider openai --model YOUR_AVAILABLE_MODEL --question "Help me reconstruct this step"
```

Default offline output is a labeled reference prompt using authored probes,
not an LLM-generated lesson. The explicitly selected OpenAI provider uses the
Responses API and `OPENAI_API_KEY` from the environment. It sends the question
and compact context, omitting raw evidence, full history, identity and paths;
it sets `store: false`, caps output and never retries a paid request. That
setting concerns response storage, not a general zero-retention guarantee.
Choose an available model yourself. Account access, prices and a model default
are not assumed. API text has no write tools and cannot become evidence without
separately observing and recording the learner's actual response.

API shape follows official [OpenAI text generation documentation](https://developers.openai.com/api/docs/guides/text)
and [Responses reference](https://developers.openai.com/api/reference/resources/responses/methods/create).
Transport tests use fictional responses, including failures and refusals.

The repository-maintained [study-tutor Skill](../skills/study-tutor/SKILL.md)
loads context, teaches with graded hints and checks receipts. Copy/install it
using a compatible host's instructions. Other clients can use the instructions
with their own tools; native installation everywhere is not promised. The
Skill grants no repository access and carries no OpenAI certification.

## Adoption and rollback

- The old 1.0 evidence, reducer, mobile operations and scheduler stay compatible.
  No automatic historical migration or production Vault changes are introduced.
- Learner identity, course packages, model reports and explicit FSRS rating
  inputs have independent 1.0 contracts. A course cannot register new subject
  enums or bypass private activation policy.
- Existing Vaults need reviewed configuration/course adoption and a separate
  exact-lock upgrade after release. Existing remote workflows do not yet persist
  these new paths automatically. This implementation does not adopt itself.
- Reverting the added modules leaves old evidence readable. Keep immutable
  requests/receipts/history; remove only regenerable reports to discard models.
- Remaining limits: authored rather than automatically verified generated
  probes, selected-task skill risk rather than a full cognitive model, and
  unvalidated recall assumptions. Demonstration metrics are not evidence of
  personal or population learning effectiveness.
