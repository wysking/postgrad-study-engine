# Awesome-list submission drafts

Status: not submitted. The repository maintainer is the submitter; disclose
self-promotion in both destinations. These are source-review suggestions, not
claims of independent educational evaluation or acceptance by either list.

## 1. open-spaced-repetition/awesome-fsrs

Destination: https://github.com/open-spaced-repetition/awesome-fsrs

The current README accepts Issue or PR suggestions. This project wraps pinned
py-fsrs rather than implementing a new FSRS algorithm. Ask for an appropriate
Application/resource placement, not an Implementation listing. A CLI application
category already contains scripted workflows, but final placement belongs to
its maintainers. Check for an existing entry or open suggestion before posting.

Proposed title: `Suggest Postgrad Study Engine — optional py-fsrs adapter in an evidence-based study workflow`

Proposed body:

> I maintain Postgrad Study Engine and am suggesting it as an experimental
> application/resource, not a new FSRS implementation.
>
> Repository: https://github.com/wysking/postgrad-study-engine
>
> The Python study CLI combines private learning archives, qualified atomic
> recall modeling, chronological evaluation and authored diagnostic probes.
> Its optional py-fsrs 6.3.2 adapter requires observed ease ratings linked to
> existing eligible events; it does not infer Good/Easy from correctness.
> Default-parameter replay is chronological, and optimized training scores
> are explicitly labeled in-sample rather than held-out validation.
>
> Reproducible setup and assumptions:
> https://github.com/wysking/postgrad-study-engine/blob/main/docs/LEARNING_MODELS.md
>
> There is no Anki deck UI, default FSRS takeover of the global scheduler or
> demonstrated human learning gain. The public demo is fictional. I would
> welcome the maintainers' judgment on whether this fits the list.

Possible concise entry:

`[Postgrad Study Engine](https://github.com/wysking/postgrad-study-engine) — Experimental Python study workflow with private evidence archives and an optional explicit-rating py-fsrs adapter; chronological replay and uncalibrated outputs.`

## 2. KaynXu/awesome-ai-education

Destination: https://github.com/KaynXu/awesome-ai-education

Follow its current `CONTRIBUTING.md`, `docs/criteria.md` and project suggestion
form. Request **Open Source**, accepting Watchlist placement if the maintainer
prefers. Do not request Field Evidence or Independent Evaluation; there is no
named public educational deployment study. Human maintainers decide inclusion.

### Project name

Postgrad Study Engine

### Primary public URL

https://github.com/wysking/postgrad-study-engine

### Requested layer

Open Source (Watchlist is acceptable at the maintainer's discretion)

### Target users

Independent learners and developers building evidence-based tutoring workflows,
including Kaoyan postgraduate-exam preparation. Each learner uses an independent
private Vault; no centralized hosted account service is supplied.

### Education workflow

Initialize an empty archive, install authored course units, teach/check actual
work, save observed evidence through matching receipts, rebuild learner-specific
context and inspect a small set of diagnostic probes. Independent solving,
assisted success, transfer and delayed retention are kept distinct.

### Role of AI

A repository teaching Skill and an opt-in OpenAI Responses adapter support
explanation and graded hints using compact context. Generated teaching text does
not automatically become learner evidence. The local Core performs deterministic
validation, recall fitting, replay and probe ranking.

### Best public evidence URL

https://github.com/wysking/postgrad-study-engine/blob/main/docs/RELEASE_REVIEW_0_5_0.md

### Evidence owner

Open-source maintainers. Evidence type: inspectable source, setup path, software
tests and fictional/synthetic demonstrations. No independent human outcome study.

### Access or open-source status

Open source with a license and setup path. Python code is MIT; documentation,
protocols, schemas and templates are CC BY 4.0. Optional API usage requires the
user's own model access/key and may incur provider charges.

### Your affiliation

Repository maintainer; self-submission. No external endorsement is asserted.

### Self-promotion or material relationship

Yes, disclosed in the affiliation field.

### Confirmation

- Supports a concrete tutoring/learning workflow, rather than general AI literacy.
- Public URLs and claims can be reviewed by a human maintainer.
- Fitted predictions remain uncalibrated; improved scores/time savings are unverified.
