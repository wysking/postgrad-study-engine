# Postgrad Study Engine

[简体中文](README.md) · [English](README.en.md)

**Make today's questions the starting point for tomorrow's learning.**

An open-source AI learning project for postgraduate entrance preparation and long-term self-study: ask questions as usual, save what actually happened, review those records periodically, and carry the resulting understanding into the next lesson.

Lightweight means an easy recording process. Preserve useful work, reasoning, hints, mistakes, corrections and study strategies whenever they actually occur. The learner can focus on learning while saving and later analysis run separately.

[Everyday use](#everyday-use) · [Try the demo](#try-it-first) · [Set up your archive](docs/GETTING_STARTED.md) · [Configure periodic review](docs/EVERYDAY_LEARNING.md#english-setup-guide)

[![Release](https://img.shields.io/github/v/release/wysking/postgrad-study-engine)](https://github.com/wysking/postgrad-study-engine/releases)
[![Core tests](https://github.com/wysking/postgrad-study-engine/actions/workflows/test.yml/badge.svg?branch=main)](https://github.com/wysking/postgrad-study-engine/actions/workflows/test.yml)
[![Code: MIT](https://img.shields.io/badge/Code-MIT-green)](LICENSE)
[![Docs: CC BY 4.0](https://img.shields.io/badge/Docs-CC_BY_4.0-lightgrey)](LICENSE-DOCS-CC-BY-4.0)

![Postgrad Study Engine: learning records and continuity](docs/assets/social-preview.jpg)

## Everyday use

### 1. Ask, solve and discuss

Bring a problem, check your steps, explore a concept, or present a complete solution. The AI explains and responds to the question at hand. Targeted follow-up practice is available when useful.

### 2. Save what happened

A straightforward solution can produce a brief note. A longer exchange can retain the initial construction, important reasoning, hints received, coefficient errors and later understanding. Record measured time when available; otherwise leave it unknown. Saving does not require completing an assessment checklist.

This is a **fictional example**:

> Practised differentiating a composite function. Initially omitted the inner derivative. After the AI pointed to the chain rule, I added the missing factor and recalculated correctly. Time was not recorded.

That is already a useful learning record. The assisted correction is preserved with its actual context.

### 3. Review periodically

With a separate GPT reviewer configured, accumulated notes can be read together. The reviewer connects stages of the same problem, identifies recent progress and recurring difficulties, and updates a source-linked written learner context. Review can run daily or at another suitable interval.

### 4. Continue with context

The next conversation reads the latest learner context and relevant source records. The AI can choose more appropriate explanations, hints and review work. Learners can correct its interpretation at any time. Original records remain available as later judgments evolve.

The [everyday learning guide](docs/EVERYDAY_LEARNING.md#english-setup-guide) explains how to connect these steps.

## Records, written context and numerical models

| Part | What it preserves or produces | When it is used |
| --- | --- | --- |
| Study records | Actual problem context, steps, hints, mistakes, corrections and any observed timing | Everyday saving; notes may be brief or detailed |
| GPT learner context | Connections across records, recent observations, teaching suggestions and hypotheses to check | Independent review and future conversations |
| Formal events and numerical models | Qualified assessment evidence, rebuildable state, recall and skill references | Formal assessment, model analysis and scheduling |

**Saving does not depend on analysis succeeding.** GPT interpretation and numerical modeling run separately. Current numerical models primarily read formal events; open notes do not automatically become mastery scores. An assisted success does not establish independent solving or long-term retention.

## What this repository provides

The public **Core** supplies reusable tools. Each learner's **Vault** stores their private materials and history. Keeping them separate helps preserve an archive across devices and interaction tools.

| Capability | Current status |
| --- | --- |
| Open factual records | Implemented through `save_study_record`, independently of complete assessment |
| Formal evidence and state rebuilding | Implemented; independent work, assisted performance and diagnosis evidence remain distinct |
| Duplicate-request handling and save confirmation | Implemented in tools and workflows; an ordinary successful save can receive a brief confirmation |
| Local demo, CLI and HTML reports | Available in v0.5.0 |
| Prerequisites and targeted probes | Contracts and examples available; actual coverage depends on the configured course |
| Recall fitting, optional FSRS and skill references | Experimental v0.5.0 capabilities; human calibration and learning effects remain unverified |
| Periodic GPT reading and written context updates | A [setup pattern](docs/EVERYDAY_LEARNING.md#english-setup-guide); configure it separately in your AI and storage environment |

The current release is [v0.5.0](https://github.com/wysking/postgrad-study-engine/releases/tag/v0.5.0). Deliverables are Python tools, documentation and integration patterns. Hosted accounts, GitHub archival workflows and scheduled GPT tasks require separate setup; downloading the code does not activate those services.

## Try it first

You need Git and Python 3.12. The baseline runtime uses the Python standard library.

```sh
git clone --branch v0.5.0 https://github.com/wysking/postgrad-study-engine.git
cd postgrad-study-engine
python -m scripts.study demo --vault ../fictional-study-demo
```

Open `reports/demo.html` inside the demo directory. It shows a **fictional learning history** across 14 elapsed days, separating independent success, assisted correction, later failure and retesting. Use a destination that does not already exist; the demo refuses to overwrite a directory.

This demonstrates Core recording and model behavior. It does not run a cloud GPT review or import real learner data.

## Build your own archive

Use the [first-time setup guide](docs/GETTING_STARTED.md) to create an empty private Vault, then choose how to use it:

- **Locally:** save records, inspect state and generate reports with the CLI.
- **During conversations:** connect an AI interface to your storage and archival workflow, then save observed work during normal teaching.
- **With periodic review:** authorize a separate GPT task to read records and update analysis files; future conversations read that context.

A cloud reviewer needs an environment that can call the model and access the private repository in the background. A local task needs its computer available when it runs. See the [setup guide](docs/EVERYDAY_LEARNING.md#english-setup-guide) for integration, access scope and a first trial run.

## Questions

### Must every problem include timing, confidence and a diagnosis?

No. Save what is actually known. AI can organize observations already present in the conversation; it should not demand extra fields just to save a note or invent missing information.

### Will preserving detail interrupt learning?

Records use material already produced during learning. Brief work can produce a brief note; extended reasoning can retain its useful steps. Analysis runs separately, and an analysis failure does not invalidate saved facts. Integrations handle technical identifiers and confirmations; their contracts live in developer documentation.

### Does GPT automatically understand every saved note?

Saving alone does not invoke interpretation. A reviewer must have access to the source records, a defined reading scope and output destination. Future conversations must read its updated context. This requires separate configuration, and model judgments can still be wrong.

### Does a written context update mastery scores?

No. Written context is revisable teaching guidance. Formal numerical assessment has its own evidence requirements and execution path. Drafts, hints and corrections from one problem should not be counted as separate independent successes.

### Can it support other subjects?

Postgraduate entrance preparation is the starting point. The record-and-review approach also supports long-term self-study. Users configure courses, prerequisite relationships, sources and plans. The public repository does not include a complete question bank.

### Have improved exam scores been demonstrated?

No. Tests and fictional demos verify software behavior. The [synthetic calibration report](docs/CALIBRATION_REPORT_0_5_0.md) is not human validation. Recall and skill outputs remain teaching references.

## For developers

The reusable Core is public; personal profiles, real records and derived learner contexts stay in each private Vault. Formal learning events are append-only, state is rebuildable, and engine adoption is separately pinned to an exact commit.

| Topic | Entry point |
| --- | --- |
| Everyday learning and periodic review | [Setup pattern](docs/EVERYDAY_LEARNING.md#english-setup-guide) |
| Initialization, demo and local use | [First-time setup](docs/GETTING_STARTED.md), [learning tools and models](docs/LEARNING_MODELS.md) |
| Remote archival, requests and persistence | [Integration workflow](docs/MOBILE_DESKTOP_WORKFLOW.md), [mobile requests](docs/MOBILE_REQUESTS.md), [open record contract](docs/LIGHTWEIGHT_STUDY_RECORDS.md) |
| Formal evidence, courses and models | [Data contracts](docs/DATA_CONTRACTS.md), [schemas](schemas/README.md), [scheduler](docs/GLOBAL_SCHEDULER.md) |
| Releases and research directions | [Changelog](CHANGELOG.md), [model roadmap](docs/MEMORY_AND_SCHEDULING_MODEL_ROADMAP.md) |
| Maintenance and contributions | [AGENTS.md](AGENTS.md), [change protocol](docs/PROJECT_ITERATION_HANDOFF.md) |

Use [Issues](https://github.com/wysking/postgrad-study-engine/issues) and [Pull Requests](https://github.com/wysking/postgrad-study-engine/pulls) for questions and contributions. Reproductions should use fictional data. Keep personal archives and paid third-party material in private storage.

Code is licensed under [MIT](LICENSE); documentation, protocols, schemas and templates use [CC BY 4.0](LICENSE-DOCS-CC-BY-4.0). See [NOTICE](NOTICE.md) for third-party rights.
