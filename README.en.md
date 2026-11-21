# Postgrad Study Engine

[简体中文](README.md) · [English](README.en.md)

**Turn every question and derivation into structured memory for your next study session.**

An open-source, Git-backed AI study engine for postgraduate entrance exams and long-term self-study. Ask questions naturally, preserve real problem-solving steps in an append-only ledger, generate periodic source-linked learner profiles, and run deterministic forgetting-curve and priority scheduling models on demand.

[Highlights](#highlights) · [How It Works](#how-it-works) · [Quick Start](#quick-start) · [Set Up Your Vault](docs/GETTING_STARTED.md) · [Everyday & Cloud Setup](docs/EVERYDAY_LEARNING.md#english-setup-guide)

[![Release](https://img.shields.io/github/v/release/wysking/postgrad-study-engine)](https://github.com/wysking/postgrad-study-engine/releases)
[![Core tests](https://img.shields.io/github/actions/workflow/status/wysking/postgrad-study-engine/test.yml?branch=main&label=Core%20tests)](https://github.com/wysking/postgrad-study-engine/actions/workflows/test.yml)
[![Code: MIT](https://img.shields.io/badge/Code-MIT-green)](LICENSE)
[![Docs: CC BY 4.0](https://img.shields.io/badge/Docs-CC_BY_4.0-lightgrey)](LICENSE-DOCS-CC-BY-4.0)

![Postgrad Study Engine: learning records and continuity](docs/assets/social-preview.jpg)

## Highlights

- **Frictionless Capture, Rich Detail**: Everyday logging defaults to open study records (`save_study_record`) with no rigid forms—keep straightforward solutions brief, and preserve full reasoning, hint sequences, mistakes, and corrections whenever they matter.
- **Clean Core / Vault Separation**: This public Core provides reusable contracts, validation, state rebuilding, and scheduling; your personal notes, raw ledgers, and learner profiles live in your own private Vault, portable across devices and AI clients.
- **Serverless Cloud Loop**: Run locally via CLI or pair a private GitHub Vault with GitHub Actions and a native cloud bridge (such as Google Drive read-only mirrors + Gmail Drafts + scheduled Apps Script sync) for mobile tutoring, automatic archival, and overnight qualitative reviews—no hosted backend, no paid LLM API required.
- **Auditable & Rebuildable Foundation**: Append-only ledgers, idempotent request deduplication, exact same-ID receipts, deterministic state rebuilds, plus optional forgetting-curve fitting, FSRS support, and multi-subject constrained scheduling.

## How It Works

```text
  Everyday Study Chat (Mobile / Desktop AI)
        │
        ▼  Save observed work naturally (save_study_record / structured events)
  Private Git Vault (inbox → serialized Actions validation → append-only ledgers + outbox receipts)
        │
        ├──▶ Periodic Qualitative Review: links multi-turn progress and updates learner_context.md
        └──▶ Deterministic Modeling & Scheduling: rebuilds unit state, due queues, and HTML reports
        │
        ▼  Sync latest profile & state context
  Next Session Picks Up Right Where You Left Off
```

### Three Composable Layers

| Layer | What It Stores or Produces | When to Use |
| --- | --- | --- |
| **Open Study Records** (`records/study_records.jsonl`) | Problem context, actual steps, hint order, mistakes, corrections, and observed timing | Everyday logging with zero form overhead |
| **Qualitative Learner Context** (`analysis/learner_context.md` / `daily/`) | Cross-session progress, recurring pitfalls, effective explanation styles, and open questions | Daily or weekly scheduled reviews loaded at conversation start |
| **Formal Evidence & Models** (`events/` / `state/` / `exports/`) | Structured attempt and diagnosis events, multi-dimensional evidence, recall risk, and schedules | Targeted diagnostics, transfer checks, and global review planning |

> **Logging and analysis stay cleanly decoupled**: saving facts never waits on downstream analysis, and assisted completions remain distinct from independent solving so long-term feedback stays faithful.

## Quick Start

Requires Git and Python 3.12 (the core runtime uses only the Python standard library):

```sh
git clone --branch v0.5.1 https://github.com/wysking/postgrad-study-engine.git
cd postgrad-study-engine
python -m scripts.study demo --vault ../study-demo
```

Open `../study-demo/reports/demo.html` to explore a 14-day sample study timeline covering independent solving, assisted corrections, error diagnosis, state rebuilding, and prioritized review queues.

## Ways to Run

Initialize a private Vault using the [first-time setup guide](docs/GETTING_STARTED.md), then pick the workflow that fits you best:

- **Local CLI**: Use `python -m scripts.study` to save notes, inspect due work, and export standalone HTML reports.
- **Mobile Cloud Loop**: Let private Vault GitHub Actions validate `inbox/*.json` requests and emit same-ID receipts; pair with Google Drive / Gmail + Apps Script for seamless mobile AI tutoring and automatic archival.
- **Scheduled Qualitative Review**: Run a periodic review job over your accumulated ledgers to publish daily reviews and refresh `analysis/learner_context.md` for future sessions.

See the [everyday learning & review guide](docs/EVERYDAY_LEARNING.md#english-setup-guide) for full setup instructions.

## Capabilities (v0.5.1)

| Area | What Is Included |
| --- | --- |
| Open Study Records | Lightweight `save_study_record` logging with free-form summary, subject label, topic, and source provenance |
| Formal Evidence & Diagnosis | Separates independent work, assisted steps, and diagnosis revisions with isomorphic and transfer checks |
| Cross-Device Request Protocol | 9 structured `inbox` operations with idempotent deduplication, single-writer concurrency, and `outbox` receipts |
| Modeling & Scheduling | Deterministic state rebuilding, constrained multi-subject priority scheduling, optional recall fitting and FSRS |
| Reporting & Tooling | CLI entrypoint, compact context capsules, standalone HTML learning dashboard, and full unit test suite |

## Documentation

| Topic | Links |
| --- | --- |
| Getting Started & Everyday Flow | [First-Time Setup](docs/GETTING_STARTED.md) · [Everyday Learning & Review](docs/EVERYDAY_LEARNING.md#english-setup-guide) |
| Cloud Sync & Request Contracts | [Cross-Device Workflow](docs/MOBILE_DESKTOP_WORKFLOW.md) · [Mobile Requests](docs/MOBILE_REQUESTS.md) · [Open Records Contract](docs/LIGHTWEIGHT_STUDY_RECORDS.md) |
| Data Models & Scheduler | [Data Contracts](docs/DATA_CONTRACTS.md) · [Schemas](schemas/README.md) · [Learning Models](docs/LEARNING_MODELS.md) · [Global Scheduler](docs/GLOBAL_SCHEDULER.md) |
| Releases & Contributing | [Changelog](CHANGELOG.md) · [Model Roadmap](docs/MEMORY_AND_SCHEDULING_MODEL_ROADMAP.md) · [Repository Rules](AGENTS.md) |

## Contributing & License

Feedback, [Issues](https://github.com/wysking/postgrad-study-engine/issues), and [Pull Requests](https://github.com/wysking/postgrad-study-engine/pulls) are welcome.

Code is licensed under [MIT](LICENSE); documentation, protocols, and schemas are licensed under [CC BY 4.0](LICENSE-DOCS-CC-BY-4.0). Third-party attributions are listed in [NOTICE.md](NOTICE.md).
