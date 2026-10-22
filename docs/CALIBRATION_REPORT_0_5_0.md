# v0.5.0 synthetic calibration sanity report

**Status: synthetic sanity only; human calibration is unverified.** This report
checks whether the implemented fitting and scoring procedures behave sensibly
under a known generating law. It does not establish learning effectiveness,
exam correctness, human forgetting dynamics or a better real study schedule.
No private Vault or external human dataset is used.

## Reproduction and evaluation

```sh
python -m scripts.calibration_check
python -m unittest tests.test_calibration_check -v
```

The [machine-readable summary](../examples/calibration/synthetic_check.json)
follows [its independent schema](../schemas/calibration_check.schema.json).
It contains no individual histories. Source hashes identify the fictional
inputs; report identity includes configuration and model version. Tests compare
the stored metrics with regeneration to numerical tolerance.

- Model: `learning-models-0.2`; seed `20261022`; 24 fictional learners.
- Generating half-lives: 0.75, 1.5, 3, 6, 12, 24 days, repeating across learners.
- Each learner has one fixed atomic recall item and 40 delayed observations;
  gaps are drawn from 1, 2, 3, 7, 14, 21 days. Outcomes follow `R=2^(-t/H)`.
- Initial retrieval and immediate restudy after failure are explicit synthetic
  successful events, establishing anchors. The ordinary qualification pipeline
  extracts all 40 delayed samples without inventing success from failure.
- Fit only the first 20 outcomes per learner; freeze parameters and score the
  next 20. No held-out outcomes enter fitting, prior selection or policy tuning.
  A regression test flips future labels and verifies unchanged fitted inputs.
- Compare fixed three-day half-life and the known generating parameter (oracle).
  The oracle is a simulation control, not an available learner model.

## Results on 480 held-out predictions

Lower scores are better. Calibration gap is the count-weighted absolute gap
between predictions and outcomes in ten fixed equal-width bins. It depends on
binning and sampling; the full bin counts are published in the JSON.

| Predictor | Brier | Log loss | Binned absolute calibration gap |
| --- | ---: | ---: | ---: |
| Fitted half-life | 0.131125 | 0.394820 | 0.062681 |
| Fixed three-day prior | 0.203101 | 0.665088 | 0.083155 |
| Known generating parameter | 0.120020 | 0.367043 | 0.055042 |

The paired Brier difference (fitted minus fixed) is **−0.071976**. A fixed-seed,
1,000-draw learner-cluster bootstrap interval is **[−0.104641, −0.041211]**.
This uncertainty describes this fictional population only. The median absolute
log half-life error is 0.233723. The conditional nominal 90% posterior interval
contains the generating half-life in 21/24 cases (87.5%); this is a small
same-law diagnostic, not an interval coverage guarantee.

## Review finding and practical limits

Review corrected posterior numerical integration: inserting the exact prior
center makes the log-half-life grid nonuniform, so posterior weights must
include cell widths. MAP fitting itself is unchanged by this correction.
Intervals are explicitly labeled conditional and uncalibrated. Invalid direct
samples and duplicate IDs now fail before fitting.

This favorable synthetic comparison is expected when the generator follows the
model's law. It does not test model misspecification, unlogged exposure,
changing half-lives, different task difficulty, selective missingness or
transfer. No FSRS superiority comparison is made: the synthetic generator has
binary outcomes, not observed human ease grades. The global priority scheduler
produces priorities rather than recall probabilities, so its raw scores cannot
serve as Brier baselines.

The next empirical gate needs appropriately licensed and consented observations
with real attempt/assistance/process provenance, participant-separated temporal
validation, minimum sample reporting and a prospectively specified evaluation.
Keep predictions labeled uncalibrated and scheduler adoption optional until
that evidence exists. No claim about score gains or time savings is supported.
